"""
Ward Protocol - Module 4: EscrowSettlement

PREIMAGE-SHA-256 conditioned claim settlement via XRPL escrow.

Fixes:
  #1 Extracted from monolith.
  #2 pool_address passed as str — ward_signed = False, no wallet stored.
  #3 AsyncJsonRpcClient as context manager - no leaked connections.
  #6 build_unsigned_tx for all transactions — institution signs and submits.
"""

from __future__ import annotations

import json
import logging
import os as _os
from dataclasses import dataclass
from typing import Dict, Optional

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import autofill
from xrpl.models import EscrowCancel, EscrowCreate, EscrowFinish, Memo, NFTokenBurn
from xrpl.utils import str_to_hex

from ward._network import get_xrpl_url, validate_url_network_match
from ward.constants import (
    ESCROW_CANCEL_HOURS,
    ESCROW_DISPUTE_HOURS,
)
from ward.primitives import (
    ConfigurationError,
    ValidationError,
    build_unsigned_tx,
    client_context,
    get_ledger_close_time,
    validate_condition_hex,
    validate_drops_amount,
    validate_xrpl_address,
)

logger = logging.getLogger("ward.settlement")

_SECONDS_PER_HOUR = 3_600

# Redis settlement lock — prevents duplicate settlement (TOCTOU mitigation)
_settlement_redis = None
try:
    import redis as _redis

    _settlement_redis = _redis.Redis.from_url(
        _os.getenv("WARD_REDIS_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    _settlement_redis.ping()
except Exception as _redis_exc:
    _require_redis = _os.getenv("WARD_REQUIRE_REDIS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if _require_redis:
        raise ConfigurationError(
            "WARD_REQUIRE_REDIS is set but Redis is unreachable at "
            f"{_os.getenv('WARD_REDIS_URL', 'redis://localhost:6379/0')}: "
            "refusing to start with unsafe in-memory settlement locking. "
            f"Error: {_redis_exc}"
        ) from _redis_exc
    logger.warning(
        "Redis unavailable for settlement locks — falling back to in-memory "
        "(NOT safe for multi-worker/production deployments; duplicate settlements possible). "
        "Set WARD_REDIS_URL to enable distributed locking, or WARD_REQUIRE_REDIS=true to fail fast. "
        "Error: %s",
        _redis_exc,
    )
    _settlement_redis = None

_SETTLEMENT_LOCK_TTL = 3600  # 1 hour — covers dispute window


@dataclass
class EscrowRecord:
    claim_id: str
    nft_token_id: str
    pool_address: str
    claimant_address: str
    payout_drops: int
    escrow_sequence: int
    condition_hex: str
    tx_hash: str
    dispute_deadline_ripple: int = 0
    cancel_after_ripple: int = 0


class EscrowSettlement:
    """
    Manage XRPL escrow lifecycle for Ward Protocol claim payouts.

    Module 4 - Crypto-conditioned claim settlement.

    Ward NEVER learns the preimage - the claimant generates and holds it.
    The condition_hex (sha256 of preimage) is submitted by the pool.
    The fulfillment_hex (the preimage) is submitted only by the claimant.

    Timing semantics:
      dispute_deadline_ripple: pool MUST finish BEFORE this time (dispute window opens).
      cancel_after_ripple: pool can cancel AFTER this time if unclaimed.

    Tier note:
      Starter:    pool operator submits create/cancel (manual tooling).
      Standard:   hosted API wraps this module.
      Enterprise: white-label - same interface, institution keys.
    """

    def __init__(self, xrpl_url: Optional[str] = None) -> None:
        if xrpl_url is None:
            xrpl_url = get_xrpl_url()
        else:
            validate_url_network_match(xrpl_url, "xrpl_url")
        self._url = xrpl_url

    async def create_claim_escrow(
        self,
        pool_address: str,
        claimant_address: str,
        payout_drops: int,
        condition_hex: str,
        nft_token_id: str,
        claim_id: str,
    ) -> EscrowRecord:
        """
        Create a time-locked + crypto-conditioned EscrowCreate from the pool.

        dispute_deadline_ripple = current_time + ESCROW_DISPUTE_HOURS * 3600.
        Pool must finish() BEFORE that deadline (dispute window opens after).
        cancel_after_ripple = current_time + ESCROW_CANCEL_HOURS  * 3600.
        Pool can cancel() AFTER cancel_after_ripple if claimant never finished.
        """
        validate_xrpl_address(claimant_address, "claimant_address")
        validate_drops_amount(payout_drops, "payout_drops")
        validate_condition_hex(condition_hex, "condition_hex")

        async with client_context(AsyncJsonRpcClient(self._url)) as client:
            current_time = await get_ledger_close_time(client)
            dispute_deadline_ripple = current_time + (
                ESCROW_DISPUTE_HOURS * _SECONDS_PER_HOUR
            )
            cancel_after_ripple = current_time + (
                ESCROW_CANCEL_HOURS * _SECONDS_PER_HOUR
            )

            audit_memo = json.dumps(
                {"claim_id": claim_id, "nft": nft_token_id},
                separators=(",", ":"),
            )
            escrow_tx = EscrowCreate(
                account=pool_address,
                destination=claimant_address,
                amount=str(payout_drops),
                finish_after=dispute_deadline_ripple,
                cancel_after=cancel_after_ripple,
                condition=condition_hex,
                memos=[
                    Memo(
                        memo_type=str_to_hex("ward/claim-escrow"),
                        memo_data=str_to_hex(audit_memo),
                    )
                ],
            )
            escrow_tx = await autofill(escrow_tx, client)
            await build_unsigned_tx(escrow_tx, client)
            # ward_signed = False — institution signs and submits escrow_tx
            tx_hash = "unsigned"
            seq = 0

            logger.info(
                "EscrowCreate: %s  claim=%s  payout=%d drops  "
                "finish_after=%d  cancel_after=%d",
                tx_hash[:16],
                claim_id,
                payout_drops,
                dispute_deadline_ripple,
                cancel_after_ripple,
            )
            return EscrowRecord(
                claim_id=claim_id,
                nft_token_id=nft_token_id,
                pool_address=pool_address,
                claimant_address=claimant_address,
                payout_drops=payout_drops,
                escrow_sequence=seq,
                condition_hex=condition_hex,
                tx_hash=tx_hash,
                dispute_deadline_ripple=dispute_deadline_ripple,
                cancel_after_ripple=cancel_after_ripple,
            )

    async def finish_escrow(
        self,
        pool_address: str,
        claimant_address_signer: str,
        escrow_record: EscrowRecord,
        fulfillment_hex: str,
    ) -> Dict[str, str]:
        """
        Finish the escrow (release payout) before the dispute window opens.

        The pool submits EscrowFinish before finish_after_ripple; the claimant
        burns their own NFT afterward. Only the NFT holder can burn it —
        the pool cannot (tecNO_PERMISSION).

        The pool must call this BEFORE dispute_deadline_ripple.
        After dispute_deadline_ripple the dispute window opens and
        finishing is no longer allowed.

        Args:
            pool_address:    Pool operator XRPL address (institution submits EscrowFinish).
            claimant_wallet: Claimant wallet (burns their own policy NFT).
            escrow_record:   Record from create_claim_escrow.
            fulfillment_hex: Preimage fulfillment hex from the claimant.

        Returns:
            {"finish_tx": hash, "burn_tx": hash}
        """
        # TOCTOU mitigation: Redis settlement lock prevents duplicate settlement
        lock_key = f"ward:settlement:{escrow_record.claim_id}"
        if _settlement_redis is not None:
            try:
                acquired = _settlement_redis.set(
                    lock_key,
                    "locked",
                    nx=True,  # Only set if not exists
                    ex=_SETTLEMENT_LOCK_TTL,
                )
                if not acquired:
                    raise ValidationError(
                        f"Settlement already in progress for claim {escrow_record.claim_id}. "
                        "Duplicate settlement attempt rejected."
                    )
            except ValidationError:
                raise
            except Exception:
                pass  # Redis unavailable — proceed without lock

        async with client_context(AsyncJsonRpcClient(self._url)) as client:
            current_time = await get_ledger_close_time(client)

            if current_time >= escrow_record.dispute_deadline_ripple:
                deadline = escrow_record.dispute_deadline_ripple
                over = current_time - deadline
                raise ValidationError(
                    f"Escrow dispute window is open: "
                    f"deadline {deadline} passed {over}s ago "
                    f"(ledger time {current_time})"
                )

            finish_tx = EscrowFinish(
                account=pool_address,
                owner=escrow_record.pool_address,
                offer_sequence=escrow_record.escrow_sequence,
                condition=escrow_record.condition_hex,
                fulfillment=fulfillment_hex,
            )
            finish_tx = await autofill(finish_tx, client)
            await build_unsigned_tx(finish_tx, client)
            # ward_signed = False — institution signs finish_tx
            logger.info(
                "EscrowFinish unsigned: claim=%s",
                escrow_record.claim_id,
            )

            burn_tx = NFTokenBurn(
                account=claimant_address_signer,
                nftoken_id=escrow_record.nft_token_id,
                memos=[
                    Memo(
                        memo_type=str_to_hex("ward/policy-burn"),
                        memo_data=str_to_hex(
                            json.dumps(
                                {
                                    "claim_id": escrow_record.claim_id,
                                    "finish_tx": "unsigned",
                                },
                                separators=(",", ":"),
                            )
                        ),
                    )
                ],
            )
            burn_tx = await autofill(burn_tx, client)
            await build_unsigned_tx(burn_tx, client)
            # ward_signed = False — institution signs burn_tx
            logger.info("NFTokenBurn unsigned: claim=%s", escrow_record.claim_id)

        return {
            "finish_tx": "unsigned",
            "burn_tx": "unsigned",
            "ward_signed": "false",
        }

    async def cancel_escrow(
        self,
        pool_address: str,
        escrow_record: EscrowRecord,
        reason: str,
    ) -> str:
        """
        Cancel the escrow and return funds to the pool (after cancel window).

        The pool can cancel AFTER cancel_after_ripple if the claimant
        never finished the escrow.
        """
        async with client_context(AsyncJsonRpcClient(self._url)) as client:
            current_time = await get_ledger_close_time(client)
            if current_time < escrow_record.cancel_after_ripple:
                remaining = escrow_record.cancel_after_ripple - current_time
                raise ValidationError(
                    f"Escrow not yet cancellable: "
                    f"{remaining // 3600}h {(remaining % 3600) // 60}m remaining "
                    f"(ledger time {current_time} < "
                    f"cancel_after {escrow_record.cancel_after_ripple})"
                )

            cancel_tx = EscrowCancel(
                account=pool_address,
                owner=escrow_record.pool_address,
                offer_sequence=escrow_record.escrow_sequence,
                memos=[
                    Memo(
                        memo_type=str_to_hex("ward/escrow-cancel"),
                        memo_data=str_to_hex(reason[:200]),
                    )
                ],
            )
            cancel_tx = await autofill(cancel_tx, client)
            await build_unsigned_tx(cancel_tx, client)
            # ward_signed = False — institution signs cancel_tx

        logger.info(
            "EscrowCancel unsigned: claim=%s  reason=%s",
            escrow_record.claim_id,
            reason,
        )
        return "unsigned"
