"""
Ward Protocol - Module 3: ClaimValidator

9-step adversarial-hardened claim validation.
All state sourced from XRPL. No off-chain inputs trusted.

Fixes: #1 Extracted. #3 asyncio.gather for steps 1/4/9. #7 dual URI format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os as _os
from dataclasses import dataclass
from typing import Optional, Tuple

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models import AccountInfo, AccountNFTs, LedgerEntry
from xrpl.models.requests import AccountTx

from ward._network import get_xrpl_url, validate_url_network_match
from ward.constants import (
    LSF_LOAN_DEFAULT,
    MIN_COVERAGE_RATIO,
    WARD_POLICY_TAXON,
    XRPL_BASE_RESERVE_DROPS,
    XRPL_OWNER_RESERVE_DROPS,
)
from ward.coverage import has_matching_premium_payment
from ward.credentials import verify_xls70_credential, verify_xls80_domain_membership
from ward.primitives import (
    LedgerError,
    ValidationError,
    WardError,
    check_rate_limit,
    client_context,
    get_ledger_close_time,
    validate_loan_id,
    validate_nft_id,
    validate_xrpl_address,
)

logger = logging.getLogger("ward.validator")


@dataclass
class ValidationResult:
    approved: bool
    claim_payout_drops: int = 0
    vault_loss_drops: int = 0
    policy_coverage_drops: int = 0
    rejection_reason: str = ""
    steps_passed: int = 0
    rejection_memo_hex: str = ""  # Hex-encoded rejection reason for on-chain memo
    # -- Coverage derivation audit ------------------------------------------
    # Records where coverage_drops came from — always the NFT URI (immutable,
    # on-chain). Enables re-derivable receipts with zero trusted inputs.
    coverage_source: str = (
        ""  # "nft_uri_field_c" | "nft_uri_field_coverage_drops" | "missing"
    )
    # -- Compliance record (eligibility pre-gate) ---------------------------
    # Populated when the XLS-70/XLS-80 eligibility gate runs. Forms an
    # auditable, on-chain-derived record of WHAT Ward verified before
    # resolving — no human governance, fully replayable.
    credential_verified: bool = False
    credential_issuer: str = ""
    credential_type: str = ""
    domain_verified: bool = False
    domain_id: str = ""


# Sentinel returned by _step1_verify_nft_exists when NFT has wrong taxon.
_WRONG_TAXON = object()


class ClaimValidator:
    """
    Validate Ward Protocol claims against on-chain state.

    All 9 steps read directly from the XRPL ledger.
    No off-chain data is trusted.

    Input validation errors are returned as ValidationResult(approved=False)
    rather than raised as exceptions, so callers can handle them uniformly.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        if url is None:
            url = get_xrpl_url()
        else:
            validate_url_network_match(url, "url")
        self._url = url

    async def validate_claim(
        self,
        *,
        claimant_address: str,
        nft_token_id: str,
        defaulted_vault: str,
        loan_id: str,
        pool_address: str,
    ) -> ValidationResult:
        """
        Run all 9 validation steps and return a ValidationResult.

        Input validation errors are returned as ValidationResult(approved=False,
        steps_passed=0) rather than raised as exceptions.
        """
        # -- Input validation at boundary (2.10 address injection) ----------
        try:
            validate_xrpl_address(claimant_address, "claimant_address")
            validate_xrpl_address(defaulted_vault, "defaulted_vault")
            validate_xrpl_address(pool_address, "pool_address")
            validate_nft_id(nft_token_id)
            validate_loan_id(loan_id)
        except ValidationError as exc:
            return ValidationResult(
                approved=False,
                rejection_reason=str(exc),
                steps_passed=0,
            )

        # FIX #14: wrap all ledger I/O so LedgerError/WardError always returns
        # ValidationResult rather than propagating as an unhandled exception.
        try:
            async with client_context(AsyncJsonRpcClient(self._url)) as client:
                # -- Compliance audit record (populated by eligibility gate) ---
                _audit_cred_verified = False
                _audit_cred_issuer = ""
                _audit_cred_type = ""
                _audit_domain_verified = False
                _audit_domain_id = ""
                # -- Eligibility pre-gate (XLS-70 credential) -------------------
                # Opt-in via WARD_REQUIRE_CREDENTIAL. When off, behaviour is
                # unchanged. When on, the claimant must hold a valid, accepted,
                # unexpired XLS-70 credential from the configured issuer/type
                # BEFORE any of the nine conformance checks run.
                if _os.getenv("WARD_REQUIRE_CREDENTIAL", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    _cred_issuer = _os.getenv("WARD_CREDENTIAL_ISSUER", "").strip()
                    _cred_type = _os.getenv("WARD_CREDENTIAL_TYPE", "").strip()
                    if not _cred_issuer or not _cred_type:
                        return ValidationResult(
                            approved=False,
                            rejection_reason=(
                                "WARD_REQUIRE_CREDENTIAL is set but "
                                "WARD_CREDENTIAL_ISSUER/WARD_CREDENTIAL_TYPE are not configured"
                            ),
                            steps_passed=0,
                        )
                    _cred = await verify_xls70_credential(
                        client, claimant_address, _cred_issuer, _cred_type
                    )
                    if not _cred.valid:
                        logger.warning("CLAIM REJECTED eligibility: %s", _cred.reason)
                        return ValidationResult(
                            approved=False,
                            rejection_reason=f"Eligibility: {_cred.reason}",
                            steps_passed=0,
                        )
                    _audit_cred_verified = True
                    _audit_cred_issuer = _cred_issuer
                    _audit_cred_type = _cred_type
                    logger.info("Eligibility pre-gate passed (XLS-70 credential valid)")
                # -- XLS-80 permissioned-domain membership ---------------------
                if _os.getenv("WARD_REQUIRE_DOMAIN", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    _domain_id = _os.getenv("WARD_DOMAIN_ID", "").strip()
                    if not _domain_id:
                        return ValidationResult(
                            approved=False,
                            rejection_reason="WARD_REQUIRE_DOMAIN is set but WARD_DOMAIN_ID is not configured",
                            steps_passed=0,
                        )
                    _dom = await verify_xls80_domain_membership(
                        client, claimant_address, _domain_id
                    )
                    if not _dom.member:
                        logger.warning(
                            "CLAIM REJECTED eligibility (domain): %s", _dom.reason
                        )
                        return ValidationResult(
                            approved=False,
                            rejection_reason=f"Eligibility (domain): {_dom.reason}",
                            steps_passed=0,
                        )
                    _audit_domain_verified = True
                    _audit_domain_id = _domain_id
                    # If the domain match surfaced a credential, record it too.
                    if _dom.matched_issuer:
                        _audit_cred_verified = True
                        _audit_cred_issuer = _dom.matched_issuer
                        _audit_cred_type = _dom.matched_credential_type
                    logger.info("Eligibility pre-gate passed (XLS-80 domain member)")
                # Steps 1, 4, pool-info run concurrently.
                nft_data, (default_flag, vault_loss), pool_info = await asyncio.gather(
                    self._step1_verify_nft_exists(
                        client, claimant_address, nft_token_id
                    ),
                    self._step4_verify_default_flag(client, loan_id),
                    self._fetch_pool_info(client, pool_address),
                )

                if nft_data is _WRONG_TAXON:
                    return self._reject(
                        1,
                        f"Wrong NFT taxon: policy taxon mismatch (expected {WARD_POLICY_TAXON})",
                    )

                if nft_data is None:
                    return self._reject(
                        1, f"NFT {nft_token_id[:16]}... not found (burned/missing)."
                    )
                logger.info("Step 1 passed")

                metadata, meta_err = self._parse_nft_metadata(nft_data)
                if meta_err:
                    return self._reject(2, meta_err)

                expiry_err = await self._step2_check_expiry(client, metadata)
                if expiry_err:
                    return self._reject(2, expiry_err)
                # Derive coverage_drops from the NFT URI (field "c" or "coverage_drops").
                # The URI is immutable (minted with TF_BURNABLE only, tfMutable=0x10 absent)
                # so this value cannot be changed after mint. Coverage derives from
                # on-chain data — no trusted off-chain input required.
                _raw_coverage = metadata.get("coverage_drops") or metadata.get("c")
                coverage_drops = int(_raw_coverage or 0)
                coverage_source = (
                    "nft_uri_field_c"
                    if metadata.get("c")
                    else (
                        "nft_uri_field_coverage_drops"
                        if metadata.get("coverage_drops")
                        else "missing"
                    )
                )
                logger.info(
                    "coverage_drops=%d derived from NFT URI (source=%s, on-chain, immutable)",
                    coverage_drops,
                    coverage_source,
                )
                premium_err = await self._step2_verify_premium_payment(
                    client=client,
                    claimant_address=claimant_address,
                    pool_address=pool_address,
                    nft_token_id=nft_token_id,
                    coverage_drops=coverage_drops,
                )
                if premium_err:
                    return self._reject(2, premium_err)
                logger.info("Step 2 passed")

                vault_err = self._step3_verify_vault_binding(metadata, defaulted_vault)
                if vault_err:
                    return self._reject(3, vault_err)
                logger.info("Step 3 passed")

                if not default_flag:
                    return self._reject(4, "Loan default flag not set on-chain.")
                logger.info("Step 4 passed")

                if vault_loss <= 0:
                    return self._reject(5, f"Vault loss not positive: {vault_loss}")
                logger.info("Step 5 passed")

                breach_err, breached = self._step6_check_coverage_breach(
                    pool_info, defaulted_vault, min_balance=vault_loss
                )
                if breach_err and not breached:
                    return self._reject(6, breach_err)
                logger.info("Step 6 passed")

                step7_err = await self._step7_verify_nft_live(nft_data, nft_token_id)
                if step7_err:
                    return self._reject(7, step7_err)
                logger.info("Step 7 passed")

                step8_err = await self._step8_verify_claimant_holds_nft(
                    nft_data, claimant_address, nft_token_id
                )
                if step8_err:
                    return self._reject(8, step8_err)
                logger.info("Step 8 passed")

                payout = min(vault_loss, coverage_drops)

                # Step 9: rate-limit per NFT token ID (2.12) then pool solvency.
                # Rate-limit checked here so steps 1–8 (cheap chain reads) run first
                # and the window is only consumed when the claim is otherwise valid.
                try:
                    check_rate_limit(nft_token_id)
                except ValidationError as exc:
                    return self._reject(9, str(exc))

                sol_err = self._step9_check_pool_solvency(pool_info, payout)
                if sol_err:
                    return self._reject(9, sol_err)
                logger.info("Step 9 passed")

                return ValidationResult(
                    approved=True,
                    claim_payout_drops=payout,
                    vault_loss_drops=vault_loss,
                    policy_coverage_drops=coverage_drops,
                    steps_passed=9,
                    credential_verified=_audit_cred_verified,
                    credential_issuer=_audit_cred_issuer,
                    credential_type=_audit_cred_type,
                    domain_verified=_audit_domain_verified,
                    domain_id=_audit_domain_id,
                    coverage_source=coverage_source,
                )

        except LedgerError as exc:
            logger.error("LedgerError during claim validation: %s", exc)
            return ValidationResult(
                approved=False,
                rejection_reason=f"Ledger error: {exc}",
            )
        except WardError as exc:
            logger.error("WardError during claim validation: %s", exc)
            return ValidationResult(
                approved=False,
                rejection_reason=f"Ward error: {exc}",
            )

    # ------------------------------------------------------------------ #
    # Step helpers                                                         #
    # ------------------------------------------------------------------ #

    async def _step1_verify_nft_exists(self, client, claimant: str, nft_token_id: str):
        """
        Scan claimant's NFTs for the given token ID.

        Returns:
            The NFT dict if found with correct taxon.
            _WRONG_TAXON sentinel if found with wrong taxon.
            None if not found at all.
        """
        try:
            marker = None
            while True:
                kwargs: dict = dict(account=claimant, limit=400)
                if marker:
                    kwargs["marker"] = marker
                resp = await client.request(AccountNFTs(**kwargs))
                if not resp.is_successful():
                    return None
                for nft in resp.result.get("account_nfts", []):
                    if nft.get("NFTokenID", "").upper() == nft_token_id.upper():
                        if nft.get("NFTokenTaxon") != WARD_POLICY_TAXON:
                            return _WRONG_TAXON
                        return nft
                marker = resp.result.get("marker")
                if not marker:
                    break
        except Exception as exc:
            logger.error("step1 error: %s", exc)
        return None

    @staticmethod
    def _parse_nft_metadata(nft_data: dict) -> Tuple[dict, Optional[str]]:
        """
        Decode and validate the NFT URI field as Ward policy metadata.

        Supports two URI formats:
          - v0.2.x compact: {"w": "ward-v1", "v": ..., "c": ..., "e": ...}
          - legacy:         {"protocol": "ward/v1", "vault_address": ...}
        """
        uri_hex = nft_data.get("URI", "")
        if not uri_hex:
            return {}, "NFT has no URI field"
        if len(uri_hex) > 512:
            return {}, f"URI hex exceeds 512 chars: {len(uri_hex)}"
        try:
            metadata = json.loads(bytes.fromhex(uri_hex).decode("utf-8"))
            if "w" in metadata:
                schema = metadata["w"]
                if not schema.startswith("ward"):
                    return {}, f"Unknown URI schema: {schema!r}"
                return metadata, None
            if metadata.get("protocol") not in ("ward-v1", "ward/v1"):
                return {}, f"Unknown protocol: {metadata.get('protocol')!r}"
            return metadata, None
        except Exception as exc:
            return {}, f"Metadata parse error: {exc}"

    async def _step2_check_expiry(self, client, metadata: dict) -> Optional[str]:
        expiry = metadata.get("expiry_ledger_time") or metadata.get("e")
        if expiry is None:
            return "Missing expiry in metadata"
        try:
            now = await get_ledger_close_time(client)
            if int(expiry) < now:
                return f"Policy expired at ledger time {expiry} (now {now})"
            return None
        except LedgerError as exc:
            return f"Ledger time check failed: {exc}"

    async def _step2_verify_premium_payment(
        self,
        *,
        client,
        claimant_address: str,
        pool_address: str,
        nft_token_id: str,
        coverage_drops: int,
    ) -> Optional[str]:
        if coverage_drops <= 0:
            return "Policy coverage missing or invalid in metadata"

        marker = None
        while True:
            try:
                response = await client.request(
                    AccountTx(
                        account=pool_address,
                        ledger_index_min=-1,
                        ledger_index_max=-1,
                        limit=200,
                        marker=marker,
                    )
                )
            except Exception as exc:
                logger.error("premium verification error: %s", exc)
                return f"Premium verification failed: {exc}"

            if not response.is_successful():
                return "Premium verification failed: AccountTx request unsuccessful"

            transactions = response.result.get("transactions", [])
            for tx_wrapper in transactions:
                tx = tx_wrapper if isinstance(tx_wrapper, dict) else {}
                if has_matching_premium_payment(
                    tx,
                    claimant_address=claimant_address,
                    pool_address=pool_address,
                    nft_token_id=nft_token_id,
                    coverage_drops=coverage_drops,
                ):
                    return None

            marker = response.result.get("marker")
            if not marker:
                break

        return (
            "Premium payment not found on-chain for this claimant, pool, and policy NFT"
        )

    async def _step4_verify_default_flag(
        self, client, loan_id: str
    ) -> Tuple[bool, int]:
        """
        Verify loan default and compute NET depositor loss.

        Returns (default_flag_set: bool, net_depositor_loss_drops: int).

        Net depositor loss = TotalValueOutstanding minus first-loss capital
        absorbed by the LoanBroker (CoverAvailable). Ward pays on the NET
        loss, not the gross loan. Paying on the gross is the conservation
        bug HGC proved: FLC posted + depositors still charged = value created
        from nothing = vault drain.

        Field names confirmed from real XLS-65/66 Devnet objects (Jul 1 2026):
          Loan.TotalValueOutstanding  -- total owed (principal + accrued interest)
          Loan.LoanBrokerID           -- link to the LoanBroker
          Loan.Flags                  -- lsfLoanDefault bit when defaulted
          LoanBroker.CoverAvailable   -- first-loss capital available (drops)
        """
        try:
            resp = await client.request(LedgerEntry(index=loan_id))
            if not resp.is_successful():
                return False, 0
            node = resp.result.get("node", {})
            flags = int(node.get("Flags", 0))
            if not (flags & LSF_LOAN_DEFAULT):
                return False, 0

            # Gross loss = total outstanding on the defaulted loan
            gross_loss = int(
                node.get("TotalValueOutstanding")
                or node.get("PrincipalOutstanding")
                or node.get("Amount")
                or 0
            )

            # Fetch first-loss capital params from the LoanBroker.
            # Ward must be called BEFORE tfLoanDefault is submitted --
            # the default tx atomically clears TVO and executes the cover draw.
            cover_available = 0
            cover_rate_minimum = 0  # UInt32, field nth 62 (rippled server_definitions)
            cover_rate_liquidation = (
                0  # UInt32, field nth 63 (rippled server_definitions)
            )
            debt_total = gross_loss  # Conservative fallback
            loan_broker_id = node.get("LoanBrokerID", "")
            if loan_broker_id:
                try:
                    broker_resp = await client.request(
                        LedgerEntry(index=loan_broker_id)
                    )
                    if broker_resp.is_successful():
                        broker_node = broker_resp.result.get("node", {})
                        cover_available = int(broker_node.get("CoverAvailable") or 0)
                        cover_rate_minimum = int(
                            broker_node.get("CoverRateMinimum") or 0
                        )
                        cover_rate_liquidation = int(
                            broker_node.get("CoverRateLiquidation") or 0
                        )
                        debt_total = int(broker_node.get("DebtTotal") or gross_loss)
                except Exception as broker_exc:
                    logger.warning(
                        "step4: LoanBroker fetch failed (%s) -- "
                        "proceeding with cover_available=0 (conservative)",
                        broker_exc,
                    )
            # Real formula from rippled source (LoanManage.cpp defaultLoan()):
            #   minimumCover   = DebtTotal x CoverRateMinimum
            #   defaultCovered = min(minimumCover x CoverRateLiquidation, gross_loss, CoverAvailable)
            # When rates unset (0): defaultCovered = 0 (matches Devnet run exactly)
            minimum_cover = debt_total * cover_rate_minimum
            default_covered = min(
                minimum_cover * cover_rate_liquidation, gross_loss, cover_available
            )
            net_depositor_loss = gross_loss - default_covered
            logger.info(
                "step4: gross_loss=%d cover_available=%d cover_rate_min=%d "
                "cover_rate_liq=%d default_covered=%d net_depositor_loss=%d",
                gross_loss,
                cover_available,
                cover_rate_minimum,
                cover_rate_liquidation,
                default_covered,
                net_depositor_loss,
            )
            return True, net_depositor_loss
        except Exception as exc:
            logger.error("step4 error: %s", exc)
            return False, 0

    def _step6_check_coverage_breach(
        self,
        pool_info: Optional[dict],
        defaulted_vault: str,
        min_balance: int = 0,
    ) -> Tuple[Optional[str], bool]:
        """Return (error_str, breached_bool).
        Uses pool_info already fetched in asyncio.gather — no duplicate RPC call.
        When min_balance > 0, also reject if usable drops are insufficient to
        cover the claimed amount even if the pool is technically solvent.
        """
        try:
            if pool_info is None:
                return "Pool AccountInfo failed", False
            balance = int(pool_info.get("Balance", 0))
            owner_count = int(pool_info.get("OwnerCount", 0))
            reserve = XRPL_BASE_RESERVE_DROPS + (owner_count * XRPL_OWNER_RESERVE_DROPS)
            usable = balance - reserve
            if usable < 0:
                return f"Pool insolvent: usable={usable}", True
            if min_balance > 0 and usable < min_balance:
                return (
                    f"Pool has insufficient balance: usable={usable} drops "
                    f"< required={min_balance} drops",
                    False,
                )
            return None, False
        except Exception as exc:
            logger.error("step6 error: %s", exc)
            return f"Coverage breach check failed: {exc}", False

    async def _step7_verify_nft_live(
        self, nft_data, nft_token_id: str
    ) -> Optional[str]:
        """Step 7: Replay protection — verify NFT still exists (not burned).
        Uses nft_data already fetched in step 1 — no duplicate RPC call.
        """
        if nft_data is None:
            return (
                f"Replay protection failed: NFT {nft_token_id[:16]}... has been burned"
            )
        if nft_data is _WRONG_TAXON:
            return "Replay protection failed: NFT taxon mismatch"
        return None

    async def _step8_verify_claimant_holds_nft(
        self, nft_data, claimant_address: str, nft_token_id: str
    ) -> Optional[str]:
        """Step 8: Verify claimant currently holds the NFT (not transferred).
        Uses nft_data already fetched in step 1 — no duplicate RPC call.
        """
        if nft_data is None or nft_data is _WRONG_TAXON:
            return (
                f"Claimant {claimant_address[:8]}... does not currently hold "
                f"NFT {nft_token_id[:16]}..."
            )
        return None

    @staticmethod
    def _step3_verify_vault_binding(
        metadata: dict, defaulted_vault: str
    ) -> Optional[str]:
        """
        Step 3: Verify the NFT covers the specific vault being claimed against.

        Cross-vault claims are rejected: an NFT minted for vault A cannot be
        used to claim against vault B, even within a multi-vault batch.
        """
        meta_vault = metadata.get("vault_address") or metadata.get("v", "")
        if meta_vault != defaulted_vault:
            return (
                f"Cross-vault claim rejected: NFT covers {meta_vault!r}, "
                f"claim is against {defaulted_vault!r}"
            )
        return None

    def _step9_check_pool_solvency(
        self, pool_info, payout: int, *, path_available: bool = True
    ) -> Optional[str]:
        if pool_info is None:
            return "Pool info unavailable"
        if not path_available:
            return "No liquid cross-asset path available at ledger close"
        balance = int(pool_info.get("Balance", 0))
        owner_count = int(pool_info.get("OwnerCount", 0))
        reserve = XRPL_BASE_RESERVE_DROPS + (owner_count * XRPL_OWNER_RESERVE_DROPS)
        usable = balance - reserve
        if usable < payout:
            return f"Pool insolvent: usable={usable} < payout={payout}"
        ratio = usable / max(payout, 1)
        if ratio < MIN_COVERAGE_RATIO:
            return f"Pool coverage ratio {ratio:.2f} < minimum {MIN_COVERAGE_RATIO}"
        return None

    async def _fetch_pool_info(self, client, pool_address: str) -> Optional[dict]:
        try:
            resp = await client.request(AccountInfo(account=pool_address))
            if not resp.is_successful():
                return None
            return resp.result.get("account_data")
        except Exception as exc:
            logger.error("fetch_pool_info error: %s", exc)
            return None

    @staticmethod
    def _reject(step: int, reason: str) -> ValidationResult:
        logger.warning("CLAIM REJECTED step %d: %s", step, reason)
        # Encode rejection reason as hex memo for on-chain audit trail
        # Institution includes this memo when submitting any rejection acknowledgment
        import json as _json

        rejection_data = _json.dumps(
            {"ward_reject": True, "step": step, "reason": reason}, separators=(",", ":")
        )
        rejection_memo_hex = rejection_data.encode("utf-8").hex().upper()
        return ValidationResult(
            approved=False,
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=0,
            rejection_reason=reason,
            steps_passed=step - 1,
            rejection_memo_hex=rejection_memo_hex,
        )
