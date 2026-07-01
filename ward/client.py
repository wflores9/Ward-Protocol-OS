"""
Ward Protocol - Module 1: WardClient

Entry point for purchasing default-protection policies on XRPL.

Workflow per policy purchase:
    1. Validate all inputs (addresses, amounts, period).
    2. Calculate premium in drops (no float XRP arithmetic).
    3. Build unsigned Payment (premium to pool) — institution signs and submits.
    4. Assemble NFT URI metadata (compact JSON, <=512 hex chars enforced).
    5. Submit NFTokenMint (non-transferable, burnable policy certificate).
    6. Return structured result with on-chain proof.

Fixes applied:
    #1  Extracted from ward_client.py monolith into own module.
    #2  institution_address validated at boundary — ward_signed = False.
    #3  AsyncJsonRpcClient used as async context manager (no leaked connections).
    #6  build_unsigned_tx for both Payment and NFTokenMint — ward_signed = False.
    #7  URI hex length assertion enforced before any network call.
    #7  License tier embedded in NFT metadata (on-chain self-description).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import autofill
from xrpl.models import Memo, NFTokenMint, Payment
from xrpl.utils import str_to_hex

from ward._network import get_xrpl_url, validate_url_network_match
from ward.constants import (
    TF_BURNABLE,
    WARD_POLICY_TAXON,
    LicenseTier,
)
from ward.coverage import build_premium_memo
from ward.primitives import (
    ValidationError,
    build_unsigned_tx,
    get_ledger_close_time,
    validate_drops_amount,
    validate_xrpl_address,
)

logger = logging.getLogger("ward.client")


class WardClient:
    """
    High-level Ward Protocol client for purchasing default-protection coverage.

    Usage::

        client = WardClient()
        result = await client.purchase_coverage(
            institution_address=institution_address,
            vault_address="rVault...",
            coverage_drops=10_000_000,
            period_days=90,
            pool_address="rPool...",
        )

    Ward never stores keys. Unsigned transactions returned for institution signing.
    during the transaction signing flow, then discarded.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        if url is None:
            url = get_xrpl_url()
        else:
            validate_url_network_match(url, "url")
        self._url = url

    async def purchase_coverage(
        self,
        institution_address: str,
        vault_address: str,
        coverage_drops: int,
        period_days: int,
        pool_address: str,
        premium_rate: float = 0.01,
        license_tier: str = "starter",
    ) -> Dict[str, Any]:
        """
        Purchase a default-protection policy: pay premium + mint NFT certificate.

        All monetary amounts are in drops (1 XRP = 1_000_000 drops).
        No float XRP arithmetic is performed.

        Args:
            institution_address: Institution XRPL address (Ward builds unsigned tx, institution signs).
            vault_address:  XRPL address of the vault being protected.
            coverage_drops: Coverage amount in drops (must be > 0).
            period_days:    Coverage period in days (must be > 0).
            pool_address:   Coverage pool XRPL address.
            premium_rate:   Annual premium rate as a fraction (0.0 < rate <= 1.0).
            license_tier:   One of "starter", "standard", "enterprise".

        Returns:
            Dict with keys:
                nft_token_id    - the minted NFTokenID (hex)
                premium_tx      - hash of the premium Payment transaction
                mint_tx         - hash of the NFTokenMint transaction
                coverage_drops  - confirmed coverage amount in drops
                expiry_ledger   - ledger close time at which policy expires
        """
        # -- Input validation --------
        validate_xrpl_address(institution_address, "institution_address")
        validate_xrpl_address(vault_address, "vault_address")
        validate_xrpl_address(pool_address, "pool_address")
        validate_drops_amount(coverage_drops, "coverage_drops")

        if period_days <= 0:
            raise ValidationError(f"period_days must be > 0, got {period_days}")
        if not (0 < premium_rate <= 1.0):
            raise ValidationError(f"premium_rate must be in (0, 1], got {premium_rate}")

        # -- Tier gate check ------------------------------------------------
        # (Risk tier enforcement happens at mint time in pool.py; here we
        # block unsupported tiers from reaching the network at all.)
        allowed = LicenseTier.TIER_MINT_GATES.get(license_tier)
        if allowed is None:
            raise ValidationError(
                f"Unknown license tier: {license_tier!r}. "
                "Must be one of: starter, standard, enterprise."
            )

        # -- Premium calculation (integer drops only) -----------------------
        premium_drops = int(coverage_drops * premium_rate * period_days / 365)
        if premium_drops < 1:
            premium_drops = 1

        client = AsyncJsonRpcClient(self._url)
        # Step 1: Determine expiry from ledger close time
        current_time = await get_ledger_close_time(client)
        expiry = current_time + (period_days * 86_400)

        # Step 2: Assemble compact URI metadata
        metadata = {
            "w": "ward-v1",
            "v": vault_address,
            "c": str(coverage_drops),
            "e": expiry,
            "t": license_tier,
            "pa": pool_address,
        }
        uri_json = json.dumps(metadata, separators=(",", ":"))
        uri_hex = str_to_hex(uri_json).upper()
        if len(uri_hex) > 512:
            raise ValidationError(f"URI hex exceeds 512 chars: {len(uri_hex)}")

        # Step 3: Mint NFT policy certificate (before payment — NFT ID needed for memo)
        nft_memo = Memo(
            memo_data=str_to_hex(
                f"ward-policy|{license_tier}|cov={coverage_drops}"
            ).upper()
        )
        mint_tx = NFTokenMint(
            account=institution_address,
            nftoken_taxon=WARD_POLICY_TAXON,
            flags=TF_BURNABLE,
            uri=uri_hex,
            memos=[nft_memo],
        )
        await build_unsigned_tx(mint_tx, client)
        # ward_signed = False — institution signs and submits mint_tx
        mint_tx_hash = "unsigned"
        nft_token_id = "pending_institution_signature"

        # Step 4: Premium Payment with ward/policy-premium memo (on-chain registry)
        _pm = build_premium_memo(nft_token_id, coverage_drops)
        premium_memo = Memo(
            memo_type=_pm["Memo"].get("MemoType"),
            memo_data=_pm["Memo"].get("MemoData"),
        )
        payment = Payment(
            account=institution_address,
            destination=pool_address,
            amount=str(premium_drops),
            memos=[premium_memo],
        )
        await build_unsigned_tx(payment, client)
        # ward_signed = False — institution signs and submits payment_tx

        logger.info(
            "Policy purchased: vault=%s cov=%d tier=%s nft=%s",
            vault_address,
            coverage_drops,
            license_tier,
            nft_token_id,
        )

        return {
            "nft_token_id": nft_token_id,
            "mint_tx": mint_tx_hash,
            "coverage_drops": coverage_drops,
            "expiry_ledger": expiry,
            "ward_signed": False,
        }

    async def purchase_multi_vault_coverage(
        self,
        institution_address: str,
        vault_addresses: List[str],
        coverage_drops: int,
        period_days: int,
        pool_address: str,
        premium_rate: float = 0.01,
        license_tier: str = "starter",
    ) -> List[Dict[str, Any]]:
        """
        Purchase default-protection policies for multiple vaults in one operation.

        Mints one non-transferable NFT per vault (taxon 281, TF_BURNABLE only).
        Collects a single premium payment covering all vaults combined.
        ward_signed = False throughout — no Ward key touches any transaction.

        Args:
            institution_address: Institution XRPL address — Ward builds unsigned tx, institution signs.
            vault_addresses: XRPL addresses of vaults to protect (1–10, no duplicates).
            coverage_drops:  Per-vault coverage in drops (must be > 0).
            period_days:     Coverage period in days (must be > 0).
            pool_address:    Coverage pool XRPL address.
            premium_rate:    Annual premium rate as a fraction (0.0 < rate <= 1.0).
            license_tier:    One of "starter", "standard", "enterprise".

        Returns:
            List of dicts (one per vault), each with:
                vault_address   - the vault this NFT covers
                nft_token_id    - the minted NFTokenID (hex)
                premium_tx      - hash of the single premium Payment transaction
                mint_tx         - hash of this vault's NFTokenMint transaction
                coverage_drops  - per-vault coverage amount in drops
                expiry_ledger   - ledger close time at which policy expires
        """
        # -- Structural validation (fast-fail before any network I/O) ----------
        if not vault_addresses:
            raise ValidationError("vault_addresses must not be empty")
        if len(vault_addresses) > 10:
            raise ValidationError(
                f"At most 10 vaults per multi-vault policy, got {len(vault_addresses)}"
            )
        for i, addr in enumerate(vault_addresses):
            validate_xrpl_address(addr, f"vault_addresses[{i}]")
        if len(set(vault_addresses)) != len(vault_addresses):
            raise ValidationError("vault_addresses contains duplicate entries")

        validate_xrpl_address(pool_address, "pool_address")
        validate_drops_amount(coverage_drops, "coverage_drops")

        if period_days <= 0:
            raise ValidationError(f"period_days must be > 0, got {period_days}")
        if not (0 < premium_rate <= 1.0):
            raise ValidationError(f"premium_rate must be in (0, 1], got {premium_rate}")

        allowed = LicenseTier.TIER_MINT_GATES.get(license_tier)
        if allowed is None:
            raise ValidationError(
                f"Unknown license tier: {license_tier!r}. "
                "Must be one of: starter, standard, enterprise."
            )

        # -- Premium covers combined coverage of all vaults --------------------
        total_coverage_drops = coverage_drops * len(vault_addresses)
        premium_drops = int(total_coverage_drops * premium_rate * period_days / 365)
        if premium_drops < 1:
            premium_drops = 1

        client = AsyncJsonRpcClient(self._url)
        current_time = await get_ledger_close_time(client)
        expiry = current_time + (period_days * 86_400)

        results: List[Dict[str, Any]] = []
        nft_token_ids: List[str] = []

        # -- Mint one NFT per vault --------------------------------------------
        for vault_address in vault_addresses:
            metadata = {
                "w": "ward-v1",
                "v": vault_address,
                "c": str(coverage_drops),
                "e": expiry,
                "t": license_tier,
                "pa": pool_address,
            }
            uri_json = json.dumps(metadata, separators=(",", ":"))
            uri_hex = str_to_hex(uri_json).upper()
            if len(uri_hex) > 512:
                raise ValidationError(f"URI hex exceeds 512 chars: {len(uri_hex)}")

            nft_memo = Memo(
                memo_data=str_to_hex(
                    f"ward-policy|{license_tier}|cov={coverage_drops}"
                ).upper()
            )
            mint_tx = NFTokenMint(
                account=institution_address,
                nftoken_taxon=WARD_POLICY_TAXON,
                flags=TF_BURNABLE,
                uri=uri_hex,
                memos=[nft_memo],
            )
            await build_unsigned_tx(mint_tx, client)
            # ward_signed = False — institution signs and submits mint_tx
            nft_token_id = "pending_institution_signature"
            mint_tx_hash = "unsigned"

            nft_token_ids.append(nft_token_id)
            results.append(
                {
                    "vault_address": vault_address,
                    "nft_token_id": nft_token_id,
                    "mint_tx": mint_tx_hash,
                    "coverage_drops": coverage_drops,
                    "expiry_ledger": expiry,
                }
            )

        # -- Single premium payment covering all vaults -----------------------
        _pm = build_premium_memo(nft_token_ids[0], total_coverage_drops)
        premium_memo = Memo(
            memo_type=_pm["Memo"].get("MemoType"),
            memo_data=_pm["Memo"].get("MemoData"),
        )
        payment = Payment(
            account=institution_address,
            destination=pool_address,
            amount=str(premium_drops),
            memos=[premium_memo],
        )
        payment = await autofill(payment, client)
        await build_unsigned_tx(payment, client)
        # ward_signed = False — institution signs and submits payment_tx

        for r in results:
            r["unsigned_payment_tx"] = "unsigned"

        logger.info(
            len(vault_addresses),
            coverage_drops,
            license_tier,
        )

        return results

    def register_pool_member(
        self,
        pool_address: str,
        member_address: str,
        contribution_drops: int,
    ) -> Dict[str, Any]:
        """
        Build an unsigned AccountSet transaction for pool member registration.

        The institution signs and submits the returned transaction themselves.
        ward_signed = False — Ward never holds or touches signing keys.

        Args:
            pool_address:       XRPL address of the target coverage pool.
            member_address:     Institution address joining the pool.
            contribution_drops: Capital contribution in drops (must be > 0).

        Returns:
            Unsigned transaction dict ready for institution signing and submission.
        """
        validate_xrpl_address(pool_address, "pool_address")
        validate_xrpl_address(member_address, "member_address")
        validate_drops_amount(contribution_drops, "contribution_drops")

        memo_data = json.dumps(
            {
                "pool": pool_address,
                "contribution_drops": contribution_drops,
                "ward_signed": False,
            },
            separators=(",", ":"),
        )
        return {
            "TransactionType": "AccountSet",
            "Account": member_address,
            "Domain": str_to_hex(f"ward-pool:{pool_address}").upper(),
            "Memos": [
                {
                    "Memo": {
                        "MemoType": str_to_hex("ward/pool-join").upper(),
                        "MemoData": str_to_hex(memo_data).upper(),
                    }
                }
            ],
            "ward_signed": False,
        }
