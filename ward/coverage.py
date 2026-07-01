"""
ward/coverage.py — On-chain coverage registry.

Replaces the in-memory _coverage_registry in pool.py.
Coverage amounts are derived from on-chain Payment transactions
with ward/policy-premium memos. No local state — all reads
from XRPL ledger directly.

This makes coverage tracking restart-safe and auditable.

ward_signed = False — always.
"""

import logging
from typing import Optional

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.requests import AccountTx

logger = logging.getLogger(__name__)

WARD_PREMIUM_MEMO_TYPE = "ward/policy-premium"
WARD_PREMIUM_MEMO_TYPE_HEX = WARD_PREMIUM_MEMO_TYPE.encode().hex().upper()


def _decode_memo_field(hex_val: Optional[str]) -> str:
    """Decode a hex memo field to string. Returns empty string on failure."""
    if not hex_val:
        return ""
    try:
        return bytes.fromhex(hex_val).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_coverage_from_tx(tx: dict) -> Optional[tuple[str, int]]:
    """
    Extract (nft_token_id, coverage_drops) from a Payment tx with
    ward/policy-premium memo. Returns None if not a premium payment.
    """
    tx_data = tx.get("tx_json") or tx.get("tx") or tx
    if tx_data.get("TransactionType") != "Payment":
        return None

    memos = tx_data.get("Memos", [])
    for memo_wrapper in memos:
        memo = memo_wrapper.get("Memo", {})
        memo_type = _decode_memo_field(memo.get("MemoType", ""))
        if memo_type != WARD_PREMIUM_MEMO_TYPE:
            continue

        memo_data = _decode_memo_field(memo.get("MemoData", ""))
        # MemoData format: "nft_token_id:coverage_drops"
        if ":" not in memo_data:
            continue
        parts = memo_data.split(":", 1)
        if len(parts) != 2:
            continue
        nft_token_id, coverage_str = parts
        try:
            coverage_drops = int(coverage_str)
            if coverage_drops > 0 and len(nft_token_id) == 64:
                return nft_token_id, coverage_drops
        except ValueError:
            continue

    return None


def has_matching_premium_payment(
    tx: dict,
    *,
    claimant_address: str,
    pool_address: str,
    nft_token_id: str,
    coverage_drops: int,
) -> bool:
    """Return True when tx is the premium payment for the specified policy."""
    tx_data = tx.get("tx_json") or tx.get("tx") or tx
    if tx_data.get("TransactionType") != "Payment":
        return False
    if tx_data.get("Account") != claimant_address:
        return False
    if tx_data.get("Destination") != pool_address:
        return False

    amount = tx_data.get("Amount")
    if not isinstance(amount, str) or not amount.isdigit() or int(amount) <= 0:
        return False

    return _extract_coverage_from_tx(tx) == (nft_token_id, coverage_drops)


async def get_active_coverage_drops(
    pool_address: str,
    client: AsyncJsonRpcClient,
    active_nft_ids: Optional[set[str]] = None,
) -> int:
    """
    Sum coverage_drops for all active policies by reading on-chain
    Payment transactions with ward/policy-premium memos sent TO
    the pool address.

    If active_nft_ids is provided, only counts policies whose NFT
    token IDs are in the set (i.e., not yet burned/settled).

    Returns total coverage in drops.
    """
    total = 0
    marker = None

    while True:
        req = AccountTx(
            account=pool_address,
            ledger_index_min=-1,
            ledger_index_max=-1,
            limit=200,
            marker=marker,
        )
        try:
            resp = await client.request(req)
        except Exception as e:
            logger.error("Coverage registry read failed: %s", e)
            break

        transactions = resp.result.get("transactions", [])
        for tx_wrapper in transactions:
            tx = tx_wrapper if isinstance(tx_wrapper, dict) else {}
            result = _extract_coverage_from_tx(tx)
            if result is None:
                continue
            nft_token_id, coverage_drops = result
            if active_nft_ids is None or nft_token_id in active_nft_ids:
                total += coverage_drops

        marker = resp.result.get("marker")
        if not marker:
            break

    logger.debug(
        "On-chain coverage for %s: %d drops across active policies",
        pool_address,
        total,
    )
    return total


def build_premium_memo(nft_token_id: str, coverage_drops: int) -> dict:
    """
    Build the XRPL Memo object for a premium payment transaction.
    Must be included in the Payment tx that purchases coverage.

    Format: MemoType=ward/policy-premium, MemoData=nft_token_id:coverage_drops
    """
    memo_data = f"{nft_token_id}:{coverage_drops}"
    memo_data_hex = memo_data.encode().hex().upper()
    return {
        "Memo": {
            "MemoType": WARD_PREMIUM_MEMO_TYPE_HEX,
            "MemoData": memo_data_hex,
        }
    }
