"""
Ward Protocol — Resolver

Builds UnsignedTransaction after a validated claim.
Handles same-asset (direct Payment) and cross-asset (XRPL native
ripple_path_find) resolution.

ward_signed is invariantly False — Ward never holds signing keys.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple, Union

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.currencies import XRP, IssuedCurrency
from xrpl.models.requests import RipplePathFind

from ward._network import get_xrpl_url, validate_url_network_match
from ward.primitives import UnsignedTransaction, client_context

logger = logging.getLogger("ward.resolver")


def _asset_to_amount(asset: dict, drops: int) -> Union[str, IssuedCurrencyAmount]:
    """Convert asset dict + value to an xrpl-py Amount."""
    if asset.get("currency", "XRP") == "XRP":
        return str(drops)
    return IssuedCurrencyAmount(
        currency=asset["currency"],
        issuer=asset.get("issuer", ""),
        value=str(drops),
    )


def _asset_to_currency(asset: dict) -> Union[XRP, IssuedCurrency]:
    """Convert asset dict to an xrpl-py Currency for source_currencies."""
    if asset.get("currency", "XRP") == "XRP":
        return XRP()
    return IssuedCurrency(
        currency=asset["currency"],
        issuer=asset.get("issuer", ""),
    )


class Resolver:
    """
    Build unsigned payout transactions for validated Ward claims.

    Same-asset: direct Payment with no pathfinding.
    Cross-asset: ripple_path_find pre-check using XRPL native path discovery.
    If no liquid path exists at ledger close, partial_resolution=True is set
    and the caller must decide how to proceed — Ward never forces a swap.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        if url is None:
            url = get_xrpl_url()
        else:
            validate_url_network_match(url, "url")
        self._url = url

    async def build_unsigned_tx(
        self,
        *,
        pool_address: str,
        claimant_address: str,
        payout_drops: int,
        collateral_asset: dict,
        payout_asset: dict,
    ) -> UnsignedTransaction:
        """
        Build an UnsignedTransaction for a validated claim payout.

        Args:
            pool_address:      Pool account (source of funds).
            claimant_address:  Payout recipient.
            payout_drops:      Amount in drops (or IOU value units).
            collateral_asset:  {"currency": "XRP"} or
                               {"currency": "USD", "issuer": "r..."}
            payout_asset:      Same format. If it differs from
                               collateral_asset, ripple_path_find runs.

        Returns:
            UnsignedTransaction — ward_signed is always False.
            Sets partial_resolution=True when no liquid path is available.
        """
        if collateral_asset == payout_asset:
            return UnsignedTransaction(
                tx_type="Payment",
                account=pool_address,
                destination=claimant_address,
                amount_drops=payout_drops,
            )

        async with client_context(AsyncJsonRpcClient(self._url)) as client:
            paths, send_max = await self._ripple_path_find(
                client,
                source_account=pool_address,
                destination_account=claimant_address,
                payout_drops=payout_drops,
                payout_asset=payout_asset,
                collateral_asset=collateral_asset,
            )

        if paths is None:
            logger.warning(
                "No liquid path: collateral=%s payout=%s — partial_resolution=True",
                collateral_asset,
                payout_asset,
            )
            return UnsignedTransaction(
                tx_type="Payment",
                account=pool_address,
                destination=claimant_address,
                amount_drops=payout_drops,
                partial_resolution=True,
            )

        return UnsignedTransaction(
            tx_type="Payment",
            account=pool_address,
            destination=claimant_address,
            amount_drops=payout_drops,
            paths=paths,
            send_max=send_max,
        )

    @staticmethod
    async def _ripple_path_find(
        client,
        *,
        source_account: str,
        destination_account: str,
        payout_drops: int,
        payout_asset: dict,
        collateral_asset: dict,
    ) -> Tuple[Optional[list], Optional[dict]]:
        """
        Call ripple_path_find. Returns (paths, send_max) or (None, None).

        Returns (None, None) when the RPC fails or no alternatives exist
        (no liquid path at the current ledger close).
        """
        try:
            destination_amount = _asset_to_amount(payout_asset, payout_drops)
            source_currency = _asset_to_currency(collateral_asset)

            resp = await client.request(
                RipplePathFind(
                    source_account=source_account,
                    destination_account=destination_account,
                    destination_amount=destination_amount,
                    source_currencies=[source_currency],
                )
            )
            if not resp.is_successful():
                logger.warning("ripple_path_find RPC failed: %s", resp.result)
                return None, None

            alternatives = resp.result.get("alternatives", [])
            if not alternatives:
                return None, None

            best = alternatives[0]
            return best.get("paths_computed", []), best.get("source_amount")

        except Exception as exc:
            logger.error("ripple_path_find error: %s", exc)
            return None, None
