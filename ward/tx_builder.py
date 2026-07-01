"""
Transaction builder for Ward Protocol XRPL operations.

Builds unsigned/signed transactions without submitting. Use with
submit_and_wait or a client for execution.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from xrpl.models import (
    EscrowCancel,
    EscrowCreate,
    EscrowFinish,
    Memo,
    Payment,
)
from xrpl.utils import datetime_to_ripple_time, str_to_hex

from ward.primitives import ripple_time_now


@dataclass
class EscrowParams:
    """Parameters for escrow creation."""

    account: str
    destination: str
    amount: int  # drops
    finish_after: datetime
    cancel_after: Optional[datetime] = None
    memos: Optional[List[Memo]] = None


class TxBuilder:
    """
    Build XRPL transactions for Ward Protocol operations.

    Does not submit; returns transaction objects ready for signing
    and submission via xrpl.transaction.submit_and_wait().
    """

    @staticmethod
    def payment(
        account: str,
        destination: str,
        amount_drops: int,
        *,
        memos: Optional[List[Dict[str, str]]] = None,
        destination_tag: Optional[int] = None,
        invoice_id: Optional[str] = None,
    ) -> Payment:
        """
        Build a Payment transaction.

        Args:
            account: Source address
            destination: Recipient address
            amount_drops: Amount in drops
            memos: Optional list of {"type": "...", "data": "..."}
            destination_tag: Optional destination tag
            invoice_id: Optional invoice ID (hex)

        Returns:
            Unsigned Payment transaction
        """
        params: Dict[str, Any] = {
            "account": account,
            "destination": destination,
            "amount": str(amount_drops),
        }
        if destination_tag is not None:
            params["destination_tag"] = destination_tag
        if invoice_id:
            params["invoice_id"] = invoice_id
        if memos:
            params["memos"] = [
                Memo(
                    memo_type=str_to_hex(m.get("type", "")),
                    memo_data=str_to_hex(m.get("data", "")),
                )
                for m in memos
            ]
        return Payment(**params)

    @staticmethod
    def escrow_create(params: EscrowParams) -> EscrowCreate:
        """
        Build an EscrowCreate transaction.

        Args:
            params: EscrowParams with account, destination, amount, times, memos

        Returns:
            Unsigned EscrowCreate transaction
        """
        cancel_after = params.cancel_after
        if cancel_after is None:
            cancel_after = params.finish_after + timedelta(hours=72)

        tx_params: Dict[str, Any] = {
            "account": params.account,
            "destination": params.destination,
            "amount": str(params.amount),
            "finish_after": datetime_to_ripple_time(params.finish_after),
            "cancel_after": datetime_to_ripple_time(cancel_after),
        }
        if params.memos:
            tx_params["memos"] = params.memos
        return EscrowCreate(**tx_params)

    @staticmethod
    def claim_escrow(
        account: str,
        destination: str,
        amount_drops: int,
        claim_id: str,
        dispute_window_hours: int = 48,
        cancel_buffer_hours: int = 72,
    ) -> EscrowCreate:
        """
        Build a Ward claim escrow (48h dispute window).

        Args:
            account: Pool/escrow source
            destination: Claim recipient
            amount_drops: Payout in drops
            claim_id: Claim UUID for memo
            dispute_window_hours: Hours before finish
            cancel_buffer_hours: Hours after finish before cancel

        Returns:
            EscrowCreate transaction
        """
        now = datetime(2000, 1, 1) + timedelta(seconds=ripple_time_now())
        finish_after = now + timedelta(hours=dispute_window_hours)
        cancel_after = finish_after + timedelta(hours=cancel_buffer_hours)
        memos = [
            Memo(
                memo_type=str_to_hex("ward_claim_escrow"),
                memo_data=str_to_hex(f"Claim ID: {claim_id}"),
            )
        ]
        return TxBuilder.escrow_create(
            EscrowParams(
                account=account,
                destination=destination,
                amount=amount_drops,
                finish_after=finish_after,
                cancel_after=cancel_after,
                memos=memos,
            )
        )

    @staticmethod
    def escrow_finish(
        account: str,
        owner: str,
        offer_sequence: int,
        *,
        condition: Optional[str] = None,
        fulfillment: Optional[str] = None,
    ) -> EscrowFinish:
        """Build EscrowFinish to release escrowed funds."""
        params: Dict[str, Any] = {
            "account": account,
            "owner": owner,
            "offer_sequence": offer_sequence,
        }
        if condition is not None:
            params["condition"] = condition
        if fulfillment is not None:
            params["fulfillment"] = fulfillment
        return EscrowFinish(**params)

    @staticmethod
    def escrow_cancel(account: str, owner: str, offer_sequence: int) -> EscrowCancel:
        """Build EscrowCancel to return escrowed funds to owner."""
        return EscrowCancel(
            account=account,
            owner=owner,
            offer_sequence=offer_sequence,
        )
