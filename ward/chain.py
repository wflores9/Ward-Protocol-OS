"""
ward/chain.py — Chain abstraction layer.

Defines the ChainAdapter interface that each chain port must implement.
ward_signed = False on every chain — this never changes.

Usage:
    Each phase port (Flare, Hedera, Solana, Stellar, XDC) subclasses ChainAdapter
    and implements every abstract method using the chain's native RPC/SDK.
    The 9-step validation logic in ClaimValidator is chain-agnostic — only the
    RPC calls injected through this interface differ per chain.

Example:
    class XRPLAdapter(ChainAdapter):
        async def get_ledger_time(self) -> int:
            return await get_ledger_close_time(self._client)

        async def build_unsigned_escrow_create(self, ...) -> dict:
            # Returns EscrowCreate fields — institution signs, Ward never does
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PolicyCertificate:
    """Chain-agnostic representation of a Ward policy certificate."""

    token_id: str
    vault_address: str
    coverage_amount: int  # in smallest unit (drops / lamports / tinybars / stroops)
    expiry: int  # Unix timestamp
    pool_address: str
    license_tier: str
    is_transferable: bool  # must always be False for valid Ward policies


@dataclass
class ClaimResult:
    """Chain-agnostic claim validation result."""

    approved: bool
    steps_passed: int  # 0–9
    rejection_reason: Optional[str] = None
    payout_amount: Optional[int] = None  # in smallest chain unit


class ChainAdapter(ABC):
    """
    Abstract base class for Ward chain adapters.

    Each chain port (Flare, Hedera, Solana, Stellar, XDC) implements this.
    The 9-step validation logic is chain-agnostic — only the RPC calls differ.

    ward_signed = False — enforced at this layer. No adapter may sign transactions.
    Adapters build unsigned transaction dicts; institutions sign; the chain settles.
    """

    @abstractmethod
    async def get_policy_certificate(
        self, claimant_address: str, token_id: str
    ) -> Optional[PolicyCertificate]:
        """Steps 1 + 8: Verify token exists and claimant currently holds it."""
        ...

    @abstractmethod
    async def get_ledger_time(self) -> int:
        """Step 2: Get current chain timestamp — never server clock."""
        ...

    @abstractmethod
    async def is_default_confirmed(self, vault_address: str, loan_id: str) -> bool:
        """Step 4: Check if default flag is set on-chain."""
        ...

    @abstractmethod
    async def get_vault_loss(self, loan_id: str) -> int:
        """Step 5: Get total outstanding loan value in smallest chain unit."""
        ...

    @abstractmethod
    async def get_pool_balance(self, pool_address: str) -> int:
        """Steps 6 + 9: Get usable pool balance (gross balance minus chain reserve)."""
        ...

    @abstractmethod
    async def build_unsigned_escrow_create(
        self,
        pool_address: str,
        claimant_address: str,
        amount: int,
        condition_hex: str,
    ) -> dict:
        """
        Settlement: Build unsigned escrow create transaction.

        ward_signed = False — the returned dict must NOT be signed.
        The institution signs and submits; Ward is never a counterparty.
        """
        ...

    @abstractmethod
    async def build_unsigned_policy_mint(
        self,
        institution_address: str,
        vault_address: str,
        coverage_drops: int,
        period_days: int,
        pool_address: str,
        license_tier: str,
    ) -> dict:
        """Build unsigned policy NFT mint transaction. ward_signed = False."""
        ...

    @abstractmethod
    async def build_unsigned_premium_payment(
        self,
        institution_address: str,
        pool_address: str,
        premium_drops: int,
        nft_token_id: str,
    ) -> dict:
        """Build unsigned premium payment transaction. ward_signed = False."""
        ...

    @abstractmethod
    async def build_unsigned_nft_burn(
        self,
        claimant_address: str,
        nft_token_id: str,
    ) -> dict:
        """Build unsigned NFT burn for replay protection. ward_signed = False."""
        ...

    @abstractmethod
    async def verify_nft_not_burned(
        self,
        claimant_address: str,
        nft_token_id: str,
    ) -> bool:
        """Verify NFT still exists (replay protection check). Returns True if live."""
        ...

    @abstractmethod
    async def get_pool_health_ratio(
        self,
        pool_address: str,
    ) -> float:
        """Return pool health ratio (usable_balance / min_coverage). >= 1.5 required."""
        ...

    @abstractmethod
    async def verify_kyc_credential(
        self,
        depositor_address: str,
    ) -> bool:
        """Verify KYC/domain credential exists for depositor. Returns True if valid."""
        ...

    @abstractmethod
    async def build_unsigned_escrow_finish(
        self,
        claimant_address: str,
        owner_address: str,
        offer_sequence: int,
        condition_hex: str,
        fulfillment_hex: str,
    ) -> dict:
        """
        Settlement: Build unsigned escrow finish transaction.

        ward_signed = False — the returned dict must NOT be signed.
        """
        ...
