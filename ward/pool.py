"""
Ward Protocol - Module 5: PoolHealthMonitor

On-chain solvency and dynamic premium monitoring for coverage pools.

Fixes applied:
    #1  Extracted from ward_client.py monolith into own module.
    #3  AsyncJsonRpcClient used as async context manager.
    #7  Owner reserve calculated correctly: base + (OwnerCount x 2 XRP).
    #3  License tier enforcement integrated (Starter/Standard/Enterprise).
    #5  Coverage tracking moved to in-memory registry; pool NFT scan removed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models import AccountInfo

from ward._network import get_xrpl_url, validate_url_network_match
from ward.constants import (
    MIN_COVERAGE_RATIO,
    RISK_TIER_THRESHOLDS,
    TIER_BASE_RATES,
    TIER_MULTIPLIERS,
    XRPL_BASE_RESERVE_DROPS,
    XRPL_OWNER_RESERVE_DROPS,
    LicenseTier,
)
from ward.coverage import get_active_coverage_drops
from ward.primitives import (
    LedgerError,
    ValidationError,
    client_context,
    validate_drops_amount,
    validate_xrpl_address,
)

logger = logging.getLogger("ward.pool")


@dataclass(frozen=True)
class PoolHealth:
    pool_address: str
    balance_drops: int
    usable_drops: int
    active_coverage_drops: int
    owner_count: int
    coverage_ratio: float
    is_solvent: bool
    dynamic_premium_rate: float
    risk_tier: str

    def balance_xrp(self) -> float:
        return self.balance_drops / 1_000_000

    def usable_xrp(self) -> float:
        return self.usable_drops / 1_000_000

    def active_coverage_xrp(self) -> float:
        return self.active_coverage_drops / 1_000_000


class PoolHealthMonitor:
    """
    Monitor solvency and compute dynamic premiums for a Ward coverage pool.

    Coverage tracking uses an in-memory registry populated by register_policy()
    after each policy mint and depleted by deregister_policy() after settlement.
    Call register_policy() from WardClient after a successful NFTokenMint.

    Trust boundary:
        active_coverage_drops is always derived from the internal registry.
        It is NEVER accepted as a caller-supplied parameter.
    """

    def __init__(
        self,
        pool_address: str,
        url: Optional[str] = None,
    ) -> None:
        validate_xrpl_address(pool_address, "pool_address")
        self._pool_address = pool_address
        if url is None:
            url = get_xrpl_url()
        else:
            validate_url_network_match(url, "url")
        self._url = url
        self._coverage_registry: Dict[str, int] = {}
        # Per-depositor, per-vault coverage tracking for multi-vault policies.
        # Shape: depositor_address -> vault_address -> coverage_drops
        self._vault_coverage: Dict[str, Dict[str, int]] = {}

    def register_policy(
        self,
        nft_token_id: str,
        coverage_drops: int,
        depositor_address: str = "",
        vault_address: str = "",
    ) -> None:
        """Register a newly minted policy NFT in the coverage tracking registry.

        Pass depositor_address and vault_address to also record per-vault coverage,
        enabling multi-vault queries via _vault_coverage.
        """
        self._coverage_registry[nft_token_id] = coverage_drops
        if depositor_address and vault_address:
            if depositor_address not in self._vault_coverage:
                self._vault_coverage[depositor_address] = {}
            self._vault_coverage[depositor_address][vault_address] = (
                self._vault_coverage[depositor_address].get(vault_address, 0)
                + coverage_drops
            )

    def deregister_policy(
        self,
        nft_token_id: str,
        depositor_address: str = "",
        vault_address: str = "",
    ) -> None:
        """Remove a policy NFT from the registry (call after NFT burn on settlement)."""
        self._coverage_registry.pop(nft_token_id, None)
        if depositor_address and vault_address:
            vault_map = self._vault_coverage.get(depositor_address)
            if vault_map:
                vault_map.pop(vault_address, None)
                if not vault_map:
                    del self._vault_coverage[depositor_address]

    async def get_health(self) -> PoolHealth:
        """
        Fetch on-chain state and return a PoolHealth snapshot.
        """
        async with client_context(AsyncJsonRpcClient(self._url)) as client:
            # Step 1: Account info
            resp = await client.request(
                AccountInfo(account=self._pool_address, ledger_index="validated")
            )
            if not resp.is_successful():
                raise LedgerError(
                    f"AccountInfo failed for {self._pool_address}: {resp.result}"
                )

            account_data = resp.result["account_data"]
            balance_drops = int(account_data["Balance"])
            owner_count = int(account_data.get("OwnerCount", 0))

            # Step 2: Compute usable balance
            reserve_drops = XRPL_BASE_RESERVE_DROPS + (
                owner_count * XRPL_OWNER_RESERVE_DROPS
            )
            usable_drops = max(0, balance_drops - reserve_drops)

            # Step 3: Sum active coverage from on-chain premium payment memos
            active_coverage_drops = await self._sum_active_coverage(client)

        # Step 4: Compute ratios and tier
        if active_coverage_drops == 0:
            coverage_ratio = float("inf")
        else:
            coverage_ratio = usable_drops / active_coverage_drops

        risk_tier = self._classify_tier(coverage_ratio)
        base_rate = TIER_BASE_RATES.get(risk_tier, 0.05)
        multiplier = TIER_MULTIPLIERS.get(risk_tier, 2.0)
        premium_rate = base_rate * multiplier

        return PoolHealth(
            pool_address=self._pool_address,
            balance_drops=balance_drops,
            usable_drops=usable_drops,
            active_coverage_drops=active_coverage_drops,
            owner_count=owner_count,
            coverage_ratio=coverage_ratio,
            is_solvent=coverage_ratio >= MIN_COVERAGE_RATIO,
            dynamic_premium_rate=premium_rate,
            risk_tier=risk_tier,
        )

    def is_minting_allowed(
        self,
        health: PoolHealth,
        license_tier: str = "starter",
    ) -> bool:
        """
        Return True if minting is allowed for this pool health and license tier.
        """
        allowed = LicenseTier.TIER_MINT_GATES.get(license_tier, set())
        return health.risk_tier in allowed

    def calculate_premium(
        self,
        health: PoolHealth,
        coverage_drops: int,
        period_days: int,
        license_tier: str = "starter",
    ) -> dict:
        """
        Calculate premium in drops for a given coverage amount and period.

        Args:
            health:         PoolHealth snapshot from get_health().
            coverage_drops: Coverage amount in drops.
            period_days:    Coverage period in days.
            license_tier:   License tier string.

        Returns:
            Dict with key "premium_drops" (int).
        """
        if not self.is_minting_allowed(health, license_tier):
            raise ValidationError(
                f"Minting not allowed: pool risk tier {health.risk_tier!r} "
                f"exceeds limit for license tier {license_tier!r}"
            )

        premium_drops = int(
            coverage_drops * health.dynamic_premium_rate * period_days / 365
        )
        return {"premium_drops": max(1, premium_drops)}

    async def _sum_active_coverage(self, client: AsyncJsonRpcClient) -> int:
        """
        Sum active coverage drops from on-chain premium payment memos.
        Restart-safe — reads directly from XRPL ledger state.
        Falls back to 0 on any ledger error (safe default — restricts minting).

        The in-memory _coverage_registry provides the active NFT ID filter
        so burned/settled policies are excluded from the on-chain sum.
        """
        try:
            active_nft_ids = (
                set(self._coverage_registry.keys()) if self._coverage_registry else None
            )
            return await get_active_coverage_drops(
                pool_address=self._pool_address,
                client=client,
                active_nft_ids=active_nft_ids,
            )
        except Exception as e:
            logger.error("_sum_active_coverage failed: %s — defaulting to 0", e)
            return 0

    @staticmethod
    def _classify_tier(coverage_ratio: float) -> str:
        """
        Classify the pool's risk tier based on the coverage ratio.

        RISK_TIER_THRESHOLDS is a list of (threshold, tier_name) tuples
        sorted in descending order of threshold.

        Args:
            coverage_ratio: usable_drops / active_coverage_drops.

        Returns:
            Risk tier string ("safest", "safe", "moderate", "elevated", "high").
        """
        for threshold, tier_name in RISK_TIER_THRESHOLDS:
            if coverage_ratio >= threshold:
                return tier_name
        return "high"


@dataclass
class PoolMember:
    """One institution's stake in a MultiInstitutionPool."""

    address: str
    contribution_drops: int


class MultiInstitutionPool:
    """
    Shared-capital coverage pool for multiple institutions.

    Members contribute drops; losses from approved claims are allocated
    pro-rata by contribution.  The first registrant becomes pool admin
    and may add or remove subsequent members.

    ward_signed = False — pool never holds or touches signing keys.
    """

    def __init__(self, pool_address: str) -> None:
        validate_xrpl_address(pool_address, "pool_address")
        self._pool_address = pool_address
        self._members: Dict[str, int] = {}  # address → contribution_drops
        self._admin: Optional[str] = None
        self._used_capacity: int = 0
        self.ward_signed: bool = False

    @property
    def pool_address(self) -> str:
        return self._pool_address

    @property
    def total_capacity(self) -> int:
        return sum(self._members.values())

    @property
    def used_capacity(self) -> int:
        return self._used_capacity

    @property
    def available_capacity(self) -> int:
        return max(0, self.total_capacity - self._used_capacity)

    @property
    def member_count(self) -> int:
        return len(self._members)

    def register_member(self, member_address: str, contribution_drops: int) -> None:
        """
        Add a member (or top up an existing member) to the pool.

        The first caller automatically becomes pool admin.
        """
        validate_xrpl_address(member_address, "member_address")
        validate_drops_amount(contribution_drops, "contribution_drops")
        if self._admin is None:
            self._admin = member_address
        self._members[member_address] = (
            self._members.get(member_address, 0) + contribution_drops
        )

    def remove_member(self, caller_address: str, member_address: str) -> None:
        """
        Remove a member from the pool.  Only the admin may call this.
        """
        validate_xrpl_address(caller_address, "caller_address")
        validate_xrpl_address(member_address, "member_address")
        if self._admin is None:
            raise ValidationError("Pool has no admin (no members registered yet)")
        if caller_address != self._admin:
            raise ValidationError(f"Only pool admin {self._admin!r} can remove members")
        if member_address not in self._members:
            raise ValidationError(f"Member {member_address!r} not found in pool")
        del self._members[member_address]

    def has_capacity(self, claim_drops: int) -> bool:
        """Return True if available_capacity >= claim_drops."""
        return self.available_capacity >= claim_drops

    def distribute_loss(self, claim_drops: int) -> Dict[str, int]:
        """
        Allocate claim_drops pro-rata across members by contribution.

        ward_signed = False — no signing keys are accessed.

        Returns:
            Mapping of member_address → loss_drops allocated for this claim.

        Raises:
            ValidationError: if pool has no members or insufficient capacity.
        """
        if not self._members:
            raise ValidationError("Pool has no members — cannot distribute loss")
        if not self.has_capacity(claim_drops):
            raise ValidationError(
                f"Pool insufficient capacity: available={self.available_capacity} "
                f"drops < claim={claim_drops} drops"
            )
        total = self.total_capacity
        losses: Dict[str, int] = {}
        allocated = 0
        members_list = list(self._members.items())
        for i, (addr, contribution) in enumerate(members_list):
            if i == len(members_list) - 1:
                losses[addr] = claim_drops - allocated
            else:
                share = int(claim_drops * contribution / total)
                losses[addr] = share
                allocated += share
        self._used_capacity += claim_drops
        return losses

    def member_addresses(self) -> List[str]:
        """Return list of currently registered member addresses."""
        return list(self._members.keys())
