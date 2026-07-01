"""
Ward Protocol — Primitives

Architecture:
    Chain-Agnostic section: exceptions, UnsignedTransaction, rate limiting,
    crypto-conditions, client context. These have no XRPL imports.

    XRPL-Specific section: address/drops/NFT validation, ledger queries,
    Ripple epoch time. These import xrpl-py types.

ward_signed = False — Ward never signs. Institutions sign; XRPL settles.

Physical split deferred to v0.3.0 when ward/primitives_xrpl.py will be
introduced. All public symbols remain importable from ward.primitives.
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
import inspect
import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Tuple, cast

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import submit_and_wait
from xrpl.core.addresscodec import is_valid_classic_address
from xrpl.models import Ledger, ServerInfo
from xrpl.models.transactions import Transaction
from xrpl.wallet import Wallet

from ward.constants import (
    CLAIM_RATE_LIMIT_MAX,
    CLAIM_RATE_LIMIT_WINDOW_S,
    RETRYABLE_ENGINE_RESULTS,
    RIPPLE_EPOCH_OFFSET,
    XRP_MAX_DROPS,
)

logger = logging.getLogger("ward.primitives")


# ── Chain-Agnostic Primitives ─────────────────────────────────────────────────
# Pure cryptographic and business logic — ports verbatim to every chain.
# When porting: copy this section as-is. No chain-specific imports required.

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WardError(Exception):
    """Base error for all Ward Protocol exceptions."""


class ValidationError(WardError):
    """Input failed pre-condition checks (addresses, amounts, etc.)."""


class SecurityError(WardError):
    """Security invariant violation detected."""


class LedgerError(WardError):
    """XRPL ledger interaction failed."""


class ConfigurationError(WardError):
    """Required environment configuration is missing or inconsistent."""


@asynccontextmanager
async def client_context(client: object) -> AsyncIterator[AsyncJsonRpcClient]:
    """
    Yield an AsyncJsonRpcClient-compatible object whether or not it natively
    implements the async context-manager protocol.

    This keeps runtime behavior fail-closed across xrpl-py versions and also
    supports the patched client mocks used by the test suite.
    """

    enter = getattr(client, "__aenter__", None)
    exit_ = getattr(client, "__aexit__", None)

    if callable(enter) and callable(exit_):
        managed = await enter()
        try:
            yield cast(AsyncJsonRpcClient, managed)
        finally:
            await exit_(None, None, None)
        return

    try:
        yield cast(AsyncJsonRpcClient, client)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await cast(Any, result)


# ── Chain-Agnostic Data Models ────────────────────────────────────────────────


@dataclass
class UnsignedTransaction:
    """
    Ward Protocol unsigned transaction envelope.

    ward_signed is invariantly False — Ward never holds signing keys,
    never signs transactions. The institution signs; XRPL settles.

    partial_resolution=True signals no liquid cross-asset path was found
    at ledger close; the caller must decide how to proceed.
    """

    tx_type: str
    account: str
    destination: str
    amount_drops: int
    paths: Optional[list] = None
    send_max: Optional[dict] = None
    partial_resolution: bool = False
    ward_signed: bool = field(default=False, init=False)


# ── XRPL-Specific Primitives ──────────────────────────────────────────────────
# Functions that depend on xrpl-py, Ripple epoch time, or XRPL address encoding.
# When porting to a new chain: implement chain-native equivalents — do NOT import
# these. Each chain adapter (ward/chain.py ChainAdapter subclass) replaces them.

# ---------------------------------------------------------------------------
# Address and amount validators
# ---------------------------------------------------------------------------


def validate_xrpl_address(address: str, label: str = "address") -> None:
    """
    Assert that address is a valid XRPL classic address.

    Raises:
        ValidationError: if address is invalid or known-bad.
    """
    if not isinstance(address, str) or not address:
        raise ValidationError(f"{label} must be a non-empty string")
    if not is_valid_classic_address(address):
        raise ValidationError(
            f"{label} '{address}' is not a valid XRPL classic address"
        )


def validate_drops_amount(drops: int, label: str = "amount") -> None:
    """
    Assert that drops is a positive integer within XRPL limits.

    Raises:
        ValidationError: if drops is invalid.
    """
    if not isinstance(drops, int) or isinstance(drops, bool):
        raise ValidationError(f"{label} must be an integer, got {type(drops).__name__}")
    if drops <= 0:
        raise ValidationError(f"{label} must be > 0, got {drops}")
    if drops > XRP_MAX_DROPS:
        raise ValidationError(
            f"{label} {drops} exceeds maximum XRP supply ({XRP_MAX_DROPS} drops)"
        )


def validate_drops(drops: int, label: str = "amount") -> None:
    """
    Strict integer-drops validator (attack vector 2.14 — XRP unit confusion).

    Rules:
      - Must be int — floats are REJECTED (1.5 XRP != 1_500_000 drops)
      - Must be >= 0
      - Must be <= XRP_MAX_DROPS (100 billion XRP in drops)

    Raises:
        ValidationError: if any condition fails.
    """
    if isinstance(drops, bool) or not isinstance(drops, int):
        raise ValidationError(
            f"{label} must be an integer (not {type(drops).__name__}). "
            "Use drops (integer), never XRP floats."
        )
    if drops < 0:
        raise ValidationError(f"{label} must be >= 0, got {drops}")
    if drops > XRP_MAX_DROPS:
        raise ValidationError(
            f"{label} {drops} exceeds max XRP supply ({XRP_MAX_DROPS} drops)"
        )


def validate_loan_id(loan_id: str) -> None:
    """
    Assert that loan_id is a valid 64-character hex string (XRPL ledger object ID).

    Raises:
        ValidationError: if loan_id is invalid.
    """
    if not isinstance(loan_id, str) or not loan_id:
        raise ValidationError("loan_id must be a non-empty string")
    if len(loan_id) != 64:
        raise ValidationError(
            f"loan_id must be exactly 64 hex chars, got {len(loan_id)}"
        )
    if not all(c in "0123456789abcdefABCDEF" for c in loan_id):
        raise ValidationError(
            f"loan_id must be hex (0-9, a-f, A-F), got invalid chars in {loan_id!r}"
        )


def validate_nft_id(nft_id: str, label: str = "NFT token ID") -> None:
    """
    Assert that nft_id is a 64-character uppercase hex string.

    Raises:
        ValidationError: if nft_id is invalid.
    """
    if not isinstance(nft_id, str) or not nft_id:
        raise ValidationError(f"{label} must be a non-empty string")
    if len(nft_id) != 64:
        raise ValidationError(
            f"{label} must be exactly 64 hex chars, got {len(nft_id)}"
        )
    if not all(c in "0123456789ABCDEF" for c in nft_id):
        raise ValidationError(f"{label} must be uppercase hex (0-9, A-F)")


# ── Chain-Agnostic Primitives (continued) ────────────────────────────────────

# ---------------------------------------------------------------------------
# Rate limiter — per token ID  (attack vector 2.12 — rate limiting bypass)
# ---------------------------------------------------------------------------

_rate_limit_lock: threading.Lock = threading.Lock()
_rate_limit_windows: dict = {}  # nft_token_id -> deque[float]
# WARNING: In-memory rate limiter — resets on process restart.
# Not shared across distributed deployments.
# Production deployment must replace with Redis or on-chain equivalent.
# Tracked: https://github.com/wflores9/ward-protocol/issues/rate-limit-durability

_MAX_RATE_LIMIT_ENTRIES: int = 10_000
_RATE_LIMIT_EVICT_COUNT: int = 1_000


def check_rate_limit(nft_token_id: str) -> bool:
    """
    Thread-safe sliding-window rate limiter per NFT token ID.

    Allows at most CLAIM_RATE_LIMIT_MAX attempts within any CLAIM_RATE_LIMIT_WINDOW_S
    second window for a given nft_token_id.

    Memory management:
        Empty windows (all timestamps expired) are removed from the dict on access.
        If the dict exceeds _MAX_RATE_LIMIT_ENTRIES, the oldest _RATE_LIMIT_EVICT_COUNT
        entries are evicted.

    Returns:
        True if within the limit.

    Raises:
        ValidationError: if the rate limit is exceeded.
    """
    now = time.monotonic()
    with _rate_limit_lock:
        if nft_token_id not in _rate_limit_windows:
            _rate_limit_windows[nft_token_id] = collections.deque()
        window = _rate_limit_windows[nft_token_id]
        # Evict timestamps older than the window
        while window and now - window[0] >= CLAIM_RATE_LIMIT_WINDOW_S:
            window.popleft()
        # Clean up empty entries (all timestamps expired) to prevent unbounded growth.
        # Re-create the entry immediately so we can append the new timestamp below.
        if not window:
            del _rate_limit_windows[nft_token_id]
            window = collections.deque()
            _rate_limit_windows[nft_token_id] = window
        if len(window) >= CLAIM_RATE_LIMIT_MAX:
            raise ValidationError(
                f"Rate limit exceeded for NFT {nft_token_id[:16]}...: "
                f"max {CLAIM_RATE_LIMIT_MAX} attempts per {CLAIM_RATE_LIMIT_WINDOW_S}s"
            )
        window.append(now)
        # Max-size guard: evict oldest entries when dict grows too large.
        if len(_rate_limit_windows) > _MAX_RATE_LIMIT_ENTRIES:
            logger.warning(
                "Rate limit window dict exceeded %d entries — evicting %d oldest",
                _MAX_RATE_LIMIT_ENTRIES,
                _RATE_LIMIT_EVICT_COUNT,
            )
            for key in list(_rate_limit_windows.keys())[:_RATE_LIMIT_EVICT_COUNT]:
                del _rate_limit_windows[key]
    return True


def validate_wallet(wallet: object, label: str = "wallet") -> Wallet:  # XRPL-specific
    """
    Assert that wallet is an xrpl.wallet.Wallet instance with a valid address.

    Returns the wallet (typed) for use in the calling scope.

    Raises:
        ValidationError: if wallet is not a valid Wallet.
    """
    if not isinstance(wallet, Wallet):
        raise ValidationError(
            f"{label} must be an xrpl.wallet.Wallet instance, got {type(wallet).__name__}"
        )
    validate_xrpl_address(wallet.classic_address, f"{label}.classic_address")
    return wallet


# ---------------------------------------------------------------------------
# XRPL time utilities  (XRPL-specific: Ripple epoch offset, xrpl-py Ledger model)
# ---------------------------------------------------------------------------


async def get_ledger_close_time(client: AsyncJsonRpcClient) -> int:
    """
    Fetch the close_time of the most recently validated ledger.

    Tries Ledger(validated) first, then ServerInfo as fallback.

    Args:
        client: Open AsyncJsonRpcClient.

    Returns:
        Ripple epoch close_time (seconds since Jan 1 2000).

    Raises:
        LedgerError: if neither request succeeds.
    """
    try:
        resp = await client.request(Ledger(ledger_index="validated"))
        if resp.is_successful():
            close_time = resp.result.get("ledger", {}).get("close_time", 0)
            if close_time:
                return int(close_time)
    except Exception:
        pass

    try:
        resp = await client.request(ServerInfo())
        if resp.is_successful():
            validated = resp.result.get("info", {}).get("validated_ledger", {})
            close_time = validated.get("close_time", 0)
            if close_time:
                return int(close_time)
    except Exception:
        pass

    raise LedgerError(
        "Could not obtain validated-ledger close_time from XRPL node. "
        "Tried Ledger(validated) and ServerInfo."
    )


def ripple_time_now() -> int:
    """Return the current time as a Ripple epoch timestamp."""
    return int(time.time()) - RIPPLE_EPOCH_OFFSET


# ── Chain-Agnostic Primitives (continued) ────────────────────────────────────

# ---------------------------------------------------------------------------
# Crypto — PREIMAGE-SHA-256 condition / fulfillment
# RFC 3230 encoding — identical on every chain that supports hash-time-locked escrow
# ---------------------------------------------------------------------------


def make_preimage_condition(preimage: bytes) -> Tuple[str, str]:
    """
    Derive a PREIMAGE-SHA-256 condition/fulfillment pair.

    Args:
        preimage: Raw secret bytes (must be exactly 32 bytes).

    Returns:
        (condition_hex, fulfillment_hex) — both upper-case hex strings
        suitable for EscrowCreate.condition and EscrowFinish.fulfillment.

    Raises:
        ValidationError: if preimage is not exactly 32 bytes.
    """
    if len(preimage) != 32:
        raise ValidationError(f"Preimage must be exactly 32 bytes, got {len(preimage)}")

    digest = hashlib.sha256(preimage).digest()
    # PREIMAGE-SHA-256 ASN.1 encoding
    condition_bytes = (
        bytes([0xA0, 0x25, 0x80, 0x20]) + digest + bytes([0x81, 0x01, 0x20])
    )
    fulfillment_bytes = bytes([0xA0, 0x22, 0x80, 0x20]) + preimage
    return condition_bytes.hex().upper(), fulfillment_bytes.hex().upper()


def generate_claim_preimage() -> bytes:
    """Return 32 cryptographically-random bytes for a new escrow preimage."""
    return secrets.token_bytes(32)


def validate_condition_hex(condition_hex: str, label: str = "condition_hex") -> str:
    """
    Validate a PREIMAGE-SHA-256 condition hex string.
    Valid condition_hex is exactly 78 uppercase hex characters (39 bytes).
    ASN.1 prefix: A0 25 80 20 <32-byte-sha256> 81 01 20
    Raises:
        ValidationError: if condition_hex is malformed.
    """
    if not isinstance(condition_hex, str):
        raise ValidationError(f"{label} must be a string")
    hex_clean = condition_hex.upper().strip()
    if len(hex_clean) != 78:
        raise ValidationError(
            f"{label} must be 78 hex chars (PREIMAGE-SHA-256), got {len(hex_clean)}"
        )
    try:
        bytes.fromhex(hex_clean)
    except ValueError:
        raise ValidationError(f"{label} contains invalid hex characters")
    if not hex_clean.startswith("A025802"):
        raise ValidationError(
            f"{label} does not match PREIMAGE-SHA-256 ASN.1 prefix (A0258020...)"
        )
    return hex_clean


# ── XRPL-Specific Primitives (continued) ─────────────────────────────────────

# ---------------------------------------------------------------------------
# Submission with retry  (Fix #6 — retryable XRPL errors; XRPL-specific)
# ---------------------------------------------------------------------------


async def build_unsigned_tx(
    tx: Transaction,
    client: AsyncJsonRpcClient,
) -> UnsignedTransaction:
    """
    Autofill a transaction and return it unsigned.
    ward_signed = False — Ward never signs. Institution signs and submits.
    """
    from xrpl.asyncio.transaction import autofill

    filled = await autofill(tx, client)
    tx_dict = filled.to_dict()
    return UnsignedTransaction(
        tx_type=tx_dict.get("TransactionType", ""),
        account=tx_dict.get("Account", ""),
        destination=tx_dict.get("Destination", ""),
        amount_drops=int(tx_dict.get("Amount", 0) or 0),
    )


async def submit_with_retry(
    tx: Transaction,
    client: AsyncJsonRpcClient,
    wallet: Wallet,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> object:
    """
    DEPRECATED — Ward must not sign or submit transactions.
    Use build_unsigned_tx() instead and return UnsignedTransaction to institution.
    This function will be removed before mainnet.
    Submit a signed transaction with retry on retryable XRPL engine results.

    Retryable results: telINSUF_FEE_P, terRETRY, terQUEUED, terPRE_SEQ.

    Args:
        tx:           The transaction to submit (will be autofilled + signed).
        client:       Open AsyncJsonRpcClient.
        wallet:       Signing wallet.
        max_attempts: Maximum submission attempts.
        base_delay:   Initial retry delay in seconds (doubles each attempt).

    Returns:
        The successful XRPL response object.

    Raises:
        LedgerError: after all attempts fail.
    """
    import warnings

    warnings.warn(
        "submit_with_retry is deprecated and will be removed before mainnet. "
        "Use build_unsigned_tx() and return UnsignedTransaction to the institution.",
        DeprecationWarning,
        stacklevel=2,
    )
    last_exc: Optional[Exception] = None
    delay = base_delay

    for attempt in range(1, max_attempts + 1):
        try:
            response = await submit_and_wait(  # ward-signing-permitted
                tx, client, wallet
            )
        except Exception as exc:
            last_exc = exc
            logger.warning("submit attempt %d raised: %s", attempt, exc)
            if attempt < max_attempts:
                await asyncio.sleep(delay)
                delay *= 2
            continue

        engine_result = response.result.get("meta", {}).get(
            "TransactionResult", ""
        ) or response.result.get("engine_result", "")

        if response.is_successful():
            return response

        if engine_result in RETRYABLE_ENGINE_RESULTS:
            logger.warning(
                "Retryable XRPL result %s on attempt %d/%d",
                engine_result,
                attempt,
                max_attempts,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
                delay *= 2
            continue

        raise LedgerError(
            f"XRPL transaction failed with result '{engine_result}': {response.result}"
        )

    raise LedgerError(
        f"Transaction failed after {max_attempts} attempts. Last error: {last_exc}"
    )
