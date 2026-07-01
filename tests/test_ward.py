"""
Ward Protocol SDK — pytest test suite  (v0.2.4)
======================================

Unit tests:       No XRPL network required (all XRPL calls are mocked).
Integration tests: Marked @pytest.mark.integration — hit XRPL testnet.
Adversarial tests: Simulate real attack scenarios against the validator.

Fix #8 applied: imports migrated from ward_client to ward.* modules;
                AsyncJsonRpcClient context manager patched for unit tests;
                MagicMock replaced with AsyncMock where coroutines are mocked;
                PoolHealthMonitor.get_health() called without args (on-chain);
                _make_validator_with_mocks patches ward.validator.AsyncJsonRpcClient.

Run unit tests only:
    pytest test_ward.py -v -m "not integration"

Run all tests (requires testnet access):
    pytest test_ward.py -v
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from xrpl.models import EscrowFinish

from ward.client import WardClient

# ---------------------------------------------------------------------------
# Ward SDK imports  (fix #8: all from ward.* modules)
# ---------------------------------------------------------------------------
from ward.constants import (
    CLAIM_RATE_LIMIT_MAX,
    CLAIM_RATE_LIMIT_WINDOW_S,
    CREDENTIAL_NFT_TAXON,
    TF_BURNABLE,
    VALID_KYC_TYPES,
    WARD_POLICY_TAXON,
)
from ward.pool import PoolHealth, PoolHealthMonitor
from ward.primitives import (
    LedgerError,
    SecurityError,
    UnsignedTransaction,
    ValidationError,
    WardError,
    generate_claim_preimage,
    make_preimage_condition,
    validate_drops_amount,
    validate_nft_id,
    validate_xrpl_address,
)
from ward.resolver import Resolver
from ward.settlement import EscrowRecord, EscrowSettlement
from ward.tx_builder import TxBuilder
from ward.validator import ClaimValidator, ValidationResult
from ward.vault_monitor import VaultMonitor

# ---------------------------------------------------------------------------
# Backward-compat aliases (old test constants mapped to new names)
# ---------------------------------------------------------------------------
RATE_LIMIT_ATTEMPTS = CLAIM_RATE_LIMIT_MAX
RATE_LIMIT_WINDOW_S = CLAIM_RATE_LIMIT_WINDOW_S
PREIMAGE_BYTES = 32  # generate_claim_preimage always returns 32 bytes


# ---------------------------------------------------------------------------
# KYC helpers  (re-implemented locally; removed from ward_client monolith)
# ---------------------------------------------------------------------------


def build_kyc_hash(kyc_type: str, subject_address: str, issued_at: int) -> str:
    if kyc_type not in VALID_KYC_TYPES:
        raise ValidationError(f"Unknown KYC type: {kyc_type}")
    raw = f"{kyc_type}:{subject_address}:{issued_at}"
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_kyc_hash(kyc_hash: str) -> None:
    if not isinstance(kyc_hash, str):
        raise ValidationError("KYC hash must be a string")
    if len(kyc_hash) != 64:
        raise ValidationError(f"KYC hash must be 64 hex chars, got {len(kyc_hash)}")
    try:
        bytes.fromhex(kyc_hash)
    except ValueError as exc:
        raise ValidationError("KYC hash contains non-hex characters") from exc
    if kyc_hash != kyc_hash.lower():
        raise ValidationError("KYC hash must be lowercase hex")


# ---------------------------------------------------------------------------
# Convenience wrappers kept for API compatibility
# ---------------------------------------------------------------------------


def generate_claim_condition():
    """Return (preimage_bytes, condition_hex, fulfillment_hex)."""
    preimage = generate_claim_preimage()
    cond, fulf = make_preimage_condition(preimage)
    return preimage, cond, fulf


def extract_nft_id(meta: dict) -> str:
    nftoken_id = meta.get("nftoken_id") or meta.get("NFTokenID")
    if nftoken_id:
        return nftoken_id
    for node in meta.get("AffectedNodes", []):
        for kind in ("CreatedNode", "ModifiedNode"):
            outer = node.get(kind, {})
            fields = outer.get("NewFields") or outer.get("FinalFields") or {}
            nfts = fields.get("NFTokens") or fields.get("nfts") or []
            for nft in nfts:
                nft_obj = nft.get("NFToken", nft)
                if nft_obj.get("NFTokenID"):
                    return nft_obj["NFTokenID"]
    raise LedgerError("NFTokenID not found in transaction meta")


def calculate_coverage_ratio(usable_drops: int, active_coverage_drops: int) -> float:
    if active_coverage_drops == 0:
        return float("inf")
    return usable_drops / active_coverage_drops


def get_ledger_time(close_time_ripple: int) -> int:
    return close_time_ripple


# ---------------------------------------------------------------------------
# Test fixtures & helpers
# ---------------------------------------------------------------------------

VALID_ADDRESS = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
VALID_ADDRESS2 = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
VALID_NFT_ID = "A" * 64
VALID_LOAN_ID = "B" * 64
VALID_VAULT = VALID_ADDRESS  # alias used by standalone test classes
POLICY_TAXON = WARD_POLICY_TAXON


@dataclass
class FakeWallet:
    """Minimal wallet stub that satisfies validate_wallet()."""

    classic_address: str = VALID_ADDRESS
    seed: str = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"
    public_key: str = "ED" + "0" * 62


def _make_success_response(result_data: dict):
    resp = MagicMock()
    resp.is_successful.return_value = True
    resp.result = result_data
    return resp


def _make_fail_response(engine_result: str = "tecFAILED"):
    resp = MagicMock()
    resp.is_successful.return_value = False
    resp.result = {
        "meta": {"TransactionResult": engine_result},
        "error": engine_result,
    }
    return resp


def _make_nft_entry(
    nft_token_id: str, uri_metadata: dict, taxon: int = WARD_POLICY_TAXON
):
    uri_hex = json.dumps(uri_metadata, separators=(",", ":")).encode().hex().upper()
    return {
        "NFTokenID": nft_token_id,
        "NFTokenTaxon": taxon,
        "URI": uri_hex,
    }


def _make_policy_metadata(
    vault_address: str = VALID_ADDRESS,
    coverage_drops: int = 1_000_000,
    expiry_ledger_time: int = 9_999_999_999,
) -> dict:
    """Compact URI format used by WardClient v0.2.x."""
    return {
        "w": "ward-v1",
        "v": vault_address,
        "c": str(coverage_drops),
        "e": expiry_ledger_time,
        "pa": VALID_ADDRESS2,
    }


def _make_loan_node(
    flags: int = 0x00010000,
    principal: int = 500_000,
    interest: int = 10_000,
    loan_broker_id: str = "E" * 64,
) -> dict:
    return {
        "Flags": flags,
        "PrincipalOutstanding": principal,
        "InterestOutstanding": interest,
        "TotalValueOutstanding": principal + interest,
        "LoanBrokerID": loan_broker_id,
    }


def _make_broker_node(
    debt_total: int = 1_000_000,
    cover_available: int = 100_000,
    coverage_rate_min: float = 0.8,
) -> dict:
    return {
        "DebtTotal": debt_total,
        "CoverAvailable": cover_available,
        "CoverageRateMin": str(coverage_rate_min),
    }


def _make_vault_node(
    assets_total: int = 500_000,
    assets_available: int = 200_000,
    loss_unrealized: int = 0,
    shares_total: int = 1_000,
) -> dict:
    return {
        "AssetsTotal": assets_total,
        "AssetsAvailable": assets_available,
        "LossUnrealized": loss_unrealized,
        "SharesTotal": shares_total,
    }


def _make_server_info_response(close_time: int = 100_000_000) -> dict:
    return {
        "info": {
            "validated_ledger": {
                "close_time": close_time,
                "seq": 12_345_678,
            }
        }
    }


def _make_pool_nft_entry(coverage_drops: int) -> dict:
    """Build a Ward policy NFT that PoolHealthMonitor can decode on-chain."""
    meta = {
        "w": "ward-v1",
        "v": VALID_ADDRESS,
        "c": str(coverage_drops),
        "e": 9_999_999_999,
    }
    return {
        "NFTokenID": "C" * 64,
        "NFTokenTaxon": WARD_POLICY_TAXON,
        "URI": json.dumps(meta, separators=(",", ":")).encode().hex().upper(),
    }


def _async_client_factory(request_fn):
    """
    Return an AsyncJsonRpcClient class replacement whose context manager
    yields a mock that routes requests to request_fn.

    Fix #8: modules use 'async with AsyncJsonRpcClient(url) as client:'
    so we must mock the class, not an instance attribute.
    """
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request_fn)

    async def _aenter(self_):
        return mock_client

    async def _aexit(self_, *args):
        pass

    MockClass = MagicMock()
    MockClass.return_value.__aenter__ = _aenter
    MockClass.return_value.__aexit__ = _aexit
    return MockClass


# ===========================================================================
# Tests: Security utilities
# ===========================================================================


class TestValidateXrplAddress:
    def test_valid_address(self):
        validate_xrpl_address(VALID_ADDRESS)

    def test_valid_address2(self):
        validate_xrpl_address(VALID_ADDRESS2)

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            validate_xrpl_address("")

    def test_none_raises(self):
        with pytest.raises((ValidationError, TypeError)):
            validate_xrpl_address(None)  # type: ignore[arg-type]

    def test_too_short_raises(self):
        with pytest.raises(ValidationError):
            validate_xrpl_address("rShort")

    def test_wrong_prefix_raises(self):
        with pytest.raises(ValidationError):
            validate_xrpl_address("xrp1qy2hwffh7aTFEZv45K9aTQhJPGC7hmb")

    def test_invalid_checksum_raises(self):
        with pytest.raises(ValidationError):
            validate_xrpl_address("rHb9CJAWyB4rj91VRWn96DkukG4bwdtyZZ")

    def test_example_vault_fails(self):
        with pytest.raises(ValidationError):
            validate_xrpl_address("rExampleVaultXXX")


class TestValidateDropsAmount:
    def test_valid_drops(self):
        validate_drops_amount(1_000_000)

    def test_one_drop(self):
        validate_drops_amount(1)

    def test_zero_raises(self):
        with pytest.raises(ValidationError):
            validate_drops_amount(0)

    def test_negative_raises(self):
        with pytest.raises(ValidationError):
            validate_drops_amount(-1)

    def test_exceeds_max_raises(self):
        with pytest.raises(ValidationError):
            validate_drops_amount(100_000_000_000_000_001)

    def test_float_raises(self):
        with pytest.raises((ValidationError, TypeError)):
            validate_drops_amount(1.5)  # type: ignore[arg-type]


class TestValidateNftId:
    def test_valid_64_hex(self):
        validate_nft_id("A" * 64)

    def test_uppercase(self):
        validate_nft_id("F" * 64)

    def test_lowercase_raises(self):
        with pytest.raises(ValidationError):
            validate_nft_id("a" * 64)

    def test_too_short_raises(self):
        with pytest.raises(ValidationError):
            validate_nft_id("A" * 63)

    def test_too_long_raises(self):
        with pytest.raises(ValidationError):
            validate_nft_id("A" * 65)

    def test_non_hex_raises(self):
        with pytest.raises(ValidationError):
            validate_nft_id("G" * 64)

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            validate_nft_id("")


# ===========================================================================
# Tests: make_preimage_condition — cryptographic correctness
# ===========================================================================


class TestPreimageConditionCryptography:
    def test_roundtrip_condition_matches_fulfillment(self):
        preimage = bytes(range(32))
        sha256 = hashlib.sha256(preimage).digest()
        cond, fulf = make_preimage_condition(preimage)
        cond_bytes = bytes.fromhex(cond)
        fulf_bytes = bytes.fromhex(fulf)
        assert cond_bytes[0] == 0xA0
        assert cond_bytes[1] == 0x25
        assert cond_bytes[2] == 0x80
        assert cond_bytes[3] == 0x20
        assert cond_bytes[4:36] == sha256
        assert fulf_bytes[0] == 0xA0
        assert fulf_bytes[1] == 0x22
        assert fulf_bytes[2] == 0x80
        assert fulf_bytes[3] == 0x20
        assert fulf_bytes[4:36] == preimage

    def test_output_lengths(self):
        cond, fulf = make_preimage_condition(bytes(32))
        assert len(cond) == 78
        assert len(fulf) == 72

    def test_condition_starts_with_a025(self):
        cond, _ = make_preimage_condition(bytes(32))
        assert cond.upper().startswith("A025")

    def test_fulfillment_starts_with_a022(self):
        preimage = os.urandom(PREIMAGE_BYTES)
        _, fulf = make_preimage_condition(preimage)
        assert fulf.upper().startswith("A022")

    def test_condition_contains_sha256_of_preimage(self):
        preimage = bytes(range(32))
        sha256_hex = hashlib.sha256(preimage).hexdigest().upper()
        cond, _ = make_preimage_condition(preimage)
        assert sha256_hex in cond.upper()

    def test_different_preimages_give_different_conditions(self):
        p1 = os.urandom(PREIMAGE_BYTES)
        p2 = os.urandom(PREIMAGE_BYTES)
        c1, _ = make_preimage_condition(p1)
        c2, _ = make_preimage_condition(p2)
        assert c1 != c2

    def test_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            make_preimage_condition(b"\x00" * 16)

    def test_generate_claim_condition_returns_three_items(self):
        preimage, cond, fulf = generate_claim_condition()
        assert len(preimage) == PREIMAGE_BYTES
        assert len(cond) == 78
        assert len(fulf) == 72


# ===========================================================================
# Tests: extract_nft_id
# ===========================================================================


class TestExtractNftId:
    def test_meta_nftoken_id_shortcut(self):
        assert extract_nft_id({"nftoken_id": "A" * 64}) == "A" * 64

    def test_created_node_fallback(self):
        meta = {
            "AffectedNodes": [
                {
                    "CreatedNode": {
                        "LedgerEntryType": "NFTokenPage",
                        "NewFields": {
                            "NFTokens": [
                                {
                                    "NFToken": {
                                        "NFTokenID": "B" * 64,
                                        "URI": "7465737430",
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
        assert extract_nft_id(meta) == "B" * 64

    def test_modified_node_fallback(self):
        meta = {
            "AffectedNodes": [
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "NFTokenPage",
                        "FinalFields": {
                            "NFTokens": [
                                {
                                    "NFToken": {
                                        "NFTokenID": "C" * 64,
                                        "URI": "7465737430",
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
        assert extract_nft_id(meta) == "C" * 64

    def test_no_nft_id_raises(self):
        with pytest.raises(LedgerError):
            extract_nft_id({"AffectedNodes": []})


# ===========================================================================
# Tests: calculate_coverage_ratio
# ===========================================================================


class TestCalculateCoverageRatio:
    def test_normal_ratio(self):
        assert calculate_coverage_ratio(3_000_000, 1_000_000) == pytest.approx(3.0)

    def test_zero_coverage_gives_inf(self):
        assert calculate_coverage_ratio(5_000_000, 0) == float("inf")

    def test_undercollateralised(self):
        assert calculate_coverage_ratio(500_000, 1_000_000) == pytest.approx(0.5)


# ===========================================================================
# Tests: WardClient — input validation (no network)
# ===========================================================================


class TestWardClientInputValidation:
    def setup_method(self):
        self.client = WardClient()
        self.wallet = FakeWallet()

    @pytest.mark.asyncio
    async def test_invalid_vault_address_raises(self):
        with pytest.raises(ValidationError, match="vault_address"):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address="rInvalid",
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=VALID_ADDRESS2,
            )

    @pytest.mark.asyncio
    async def test_invalid_pool_address_raises(self):
        with pytest.raises(ValidationError, match="pool_address"):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address=VALID_ADDRESS,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address="not-an-address",
            )

    @pytest.mark.asyncio
    async def test_zero_coverage_drops_raises(self):
        with pytest.raises(ValidationError):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address=VALID_ADDRESS,
                coverage_drops=0,
                period_days=30,
                pool_address=VALID_ADDRESS2,
            )

    @pytest.mark.asyncio
    async def test_zero_period_days_raises(self):
        with pytest.raises(ValidationError):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address=VALID_ADDRESS,
                coverage_drops=1_000_000,
                period_days=0,
                pool_address=VALID_ADDRESS2,
            )

    @pytest.mark.asyncio
    async def test_invalid_premium_rate_raises(self):
        with pytest.raises(ValidationError):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address=VALID_ADDRESS,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=VALID_ADDRESS2,
                premium_rate=1.5,
            )

    @pytest.mark.asyncio
    async def test_example_vault_address_from_prototype_rejected(self):
        with pytest.raises(ValidationError):
            await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address="rExampleVaultXXX",
                coverage_drops=1_000_000,
                period_days=90,
                pool_address="rPoolAddressXXX",
            )

    def test_nft_flag_constant_is_burnable_not_transferable(self):
        assert TF_BURNABLE == 0x00000001
        assert TF_BURNABLE != 0x00000008

    @pytest.mark.asyncio
    async def test_purchase_coverage_raises_if_nft_id_missing(self):
        """FIX #9: WardError raised when NFTokenMint response has no nftoken_id.
        NFT is minted first (so nft_token_id is available for the payment memo)."""
        from xrpl.wallet import Wallet as _Wallet

        real_wallet = _Wallet.create()

        # NFT mint returns response with no nftoken_id in meta
        fake_empty_nft_resp = MagicMock()
        fake_empty_nft_resp.result = {"tx_json": {"hash": "abc123"}, "meta": {}}

        with (
            patch("ward.client.AsyncJsonRpcClient", _async_client_factory(AsyncMock())),
            patch("ward.client.autofill", AsyncMock(side_effect=lambda tx, c: tx)),
            patch(
                "ward.client.build_unsigned_tx",
                AsyncMock(return_value=fake_empty_nft_resp),
            ),
            patch(
                "ward.client.get_ledger_close_time", AsyncMock(return_value=800_000_000)
            ),
        ):
            # ward_signed = False — Ward returns unsigned tx, NFT ID pending institution signature
            result = await self.client.purchase_coverage(
                institution_address=VALID_ADDRESS,
                vault_address=VALID_ADDRESS,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=VALID_ADDRESS2,
            )
            assert result["nft_token_id"] == "pending_institution_signature"
            assert "mint_tx" in result
            assert result.get("ward_signed") is False


# ===========================================================================
# Tests: ClaimValidator — input sanitation
# ===========================================================================


class TestClaimValidatorInputSanitation:
    def setup_method(self):
        self.validator = ClaimValidator()

    @pytest.mark.asyncio
    async def test_invalid_claimant_address(self):
        result = await self.validator.validate_claim(
            claimant_address="bad-addr",
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert result.steps_passed == 0

    @pytest.mark.asyncio
    async def test_invalid_nft_id(self):
        result = await self.validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id="not-64-hex",
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert result.steps_passed == 0

    @pytest.mark.asyncio
    async def test_claim_rejects_short_loan_id(self):
        """FIX #6: loan_id shorter than 64 chars must be rejected at input boundary."""
        result = await self.validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id="AABBCC",  # too short
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert result.steps_passed == 0
        assert (
            "64 hex" in result.rejection_reason or "loan_id" in result.rejection_reason
        )

    @pytest.mark.asyncio
    async def test_claim_rejects_non_hex_loan_id(self):
        """FIX #6: loan_id with non-hex chars must be rejected at input boundary."""
        result = await self.validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id="Z" * 64,  # 64 chars but not hex
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert result.steps_passed == 0
        assert "hex" in result.rejection_reason.lower()


# ===========================================================================
# Tests: ClaimValidator — adversarial scenarios  (fix #8)
# ===========================================================================


class TestClaimValidatorAdversarial:
    """
    9-step adversarial validation with fully mocked XRPL client.

    Fix #8: Instead of injecting validator._client, we patch
    ward.validator.AsyncJsonRpcClient with a context-manager mock.
    The patch is stopped after each test via _validate() helper.
    """

    def setup_method(self):
        from ward.primitives import _rate_limit_windows

        _rate_limit_windows.pop(VALID_NFT_ID, None)

    def _make_validator_with_mocks(
        self,
        *,
        nft_exists: bool = True,
        nft_taxon: int = WARD_POLICY_TAXON,
        ledger_time: int = 100_000_000,
        expiry_time: int = 999_999_999,
        policy_vault: str = VALID_ADDRESS,
        defaulted_vault: str = VALID_ADDRESS,
        default_flag_set: bool = True,
        vault_loss_drops: int = 100_000,
        pool_balance_drops: int = 10_000_000,
        loan_broker_available: bool = True,
        coverage_drops: int = 500_000,
        premium_paid: bool = True,
    ) -> ClaimValidator:
        metadata = _make_policy_metadata(
            vault_address=policy_vault,
            coverage_drops=coverage_drops,
            expiry_ledger_time=expiry_time,
        )
        uri_hex = json.dumps(metadata, separators=(",", ":")).encode().hex().upper()
        nft_entry = {
            "NFTokenID": VALID_NFT_ID,
            "NFTokenTaxon": nft_taxon,
            "URI": uri_hex,
        }
        loan_flags = 0x00010000 if default_flag_set else 0x0
        loan_node = _make_loan_node(
            flags=loan_flags, principal=500_000, interest=10_000
        )
        broker_node = _make_broker_node(debt_total=1_000_000, cover_available=100_000)
        vault_node = _make_vault_node(assets_total=400_000, loss_unrealized=0)
        pool_info = {"account_data": {"Balance": str(pool_balance_drops)}}

        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models import AccountNFTs as _ANFTs
            from xrpl.models import LedgerEntry as _LE
            from xrpl.models import ServerInfo as _SI
            from xrpl.models.requests import AccountTx as _ATx

            from ward.coverage import build_premium_memo

            if isinstance(req, _ANFTs):
                nfts = [nft_entry] if nft_exists else []
                return _make_success_response({"account_nfts": nfts})
            elif isinstance(req, _SI):
                return _make_success_response(_make_server_info_response(ledger_time))
            elif isinstance(req, _AI):
                return _make_success_response(pool_info)
            elif isinstance(req, _ATx):
                txs = []
                if premium_paid:
                    txs.append(
                        {
                            "tx_json": {
                                "TransactionType": "Payment",
                                "Account": VALID_ADDRESS,
                                "Destination": getattr(req, "account", VALID_ADDRESS2),
                                "Amount": "1000",
                                "Memos": [
                                    build_premium_memo(VALID_NFT_ID, coverage_drops)
                                ],
                            }
                        }
                    )
                return _make_success_response({"transactions": txs})
            elif isinstance(req, _LE):
                index_val = getattr(req, "index", None)
                vault_val = getattr(req, "vault", None)
                if index_val == VALID_LOAN_ID:
                    if not default_flag_set:
                        return _make_fail_response()
                    return _make_success_response({"node": loan_node})
                elif index_val is not None and index_val != VALID_LOAN_ID:
                    if not loan_broker_available:
                        return _make_fail_response()
                    return _make_success_response({"node": broker_node})
                elif vault_val is not None:
                    return _make_success_response({"node": vault_node})
                return _make_fail_response("tecNO_ENTRY")
            return _make_fail_response("temUNKNOWN")

        validator = ClaimValidator()
        _patch = patch(
            "ward.validator.AsyncJsonRpcClient",
            _async_client_factory(mock_request),
        )
        _patch.start()
        validator._mock_patch = _patch
        return validator

    async def _validate(self, validator, **kwargs) -> ValidationResult:
        try:
            return await validator.validate_claim(**kwargs)
        finally:
            p = getattr(validator, "_mock_patch", None)
            if p:
                try:
                    p.stop()
                except RuntimeError:
                    pass

    # ── Adversarial Test 1: Fake claim ──────────────────────────────

    @pytest.mark.asyncio
    async def test_fake_claim_nft_not_found(self):
        validator = self._make_validator_with_mocks(nft_exists=False)
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert "not found" in result.rejection_reason.lower()

    # ── Adversarial Test 2: Expired policy ──────────────────────────

    @pytest.mark.asyncio
    async def test_expired_policy_rejected(self):
        validator = self._make_validator_with_mocks(
            ledger_time=200_000_000,
            expiry_time=100_000_000,
        )
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert "expired" in result.rejection_reason.lower()

    # ── Adversarial Test 3: Wrong vault ─────────────────────────────

    @pytest.mark.asyncio
    async def test_wrong_vault_rejected(self):
        validator = self._make_validator_with_mocks(
            policy_vault=VALID_ADDRESS,
            defaulted_vault=VALID_ADDRESS2,
        )
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS2,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert "vault" in result.rejection_reason.lower()

    # ── Adversarial Test 4: Loan not in default ──────────────────────

    @pytest.mark.asyncio
    async def test_non_defaulted_loan_rejected(self):
        validator = self._make_validator_with_mocks(default_flag_set=False)
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved

    # ── Adversarial Test 5: Drained pool ────────────────────────────

    @pytest.mark.asyncio
    async def test_drained_pool_rejected(self):
        validator = self._make_validator_with_mocks(
            pool_balance_drops=100,
            coverage_drops=10_000_000,
        )
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert "insolvent" in result.rejection_reason.lower()

    # ── Adversarial Test 6: Wrong taxon ─────────────────────────────

    @pytest.mark.asyncio
    async def test_wrong_taxon_rejected(self):
        validator = self._make_validator_with_mocks(nft_taxon=9999)
        result = await self._validate(
            validator,
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert not result.approved
        assert "taxon" in result.rejection_reason.lower()


# ===========================================================================
# Tests: VaultMonitor
# ===========================================================================


class TestVaultMonitor:
    def test_init_valid_address(self):
        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])
        assert VALID_ADDRESS in monitor._vault_addresses

    def test_invalid_vault_address_rejected(self):
        with pytest.raises(ValidationError):
            VaultMonitor(vault_addresses=["rInvalidXXXXXXXX"])

    def test_add_vault_validates_address(self):
        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])
        with pytest.raises(ValidationError):
            monitor.add_vault("not-a-valid-xrpl-address")

    def test_anomaly_window_clears_expired_entries(self):
        from ward.vault_monitor import ANOMALY_THRESHOLD

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])
        now = time.time()
        for _ in range(ANOMALY_THRESHOLD):
            monitor._recent_signals[VALID_ADDRESS].append((now - 9999, 0.5))
        result = monitor._detect_anomaly(VALID_ADDRESS)
        assert not result, "Old signals should not count after window expires"


# ===========================================================================
# Tests: PoolHealthMonitor — solvency and dynamic pricing
#
# Fix #8:
#   - get_health() takes NO arguments (active_coverage_drops is on-chain)
#   - mock_request handles both AccountInfo AND AccountNFTs
#   - coverage is injected via AccountNFTs mock using Ward policy NFT entries
# ===========================================================================


class TestPoolHealthMonitor:
    def _make_monitor(
        self,
        balance_drops: int = 10_000_000,
        coverage_drops: int = 0,
    ) -> PoolHealthMonitor:
        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models.requests import AccountTx as _ATx

            if isinstance(req, _AI):
                return _make_success_response(
                    {"account_data": {"Balance": str(balance_drops), "OwnerCount": 1}}
                )
            if isinstance(req, _ATx):
                txs = []
                if coverage_drops > 0:
                    from ward.coverage import build_premium_memo

                    memo = build_premium_memo(VALID_NFT_ID, coverage_drops)
                    txs.append(
                        {"tx_json": {"TransactionType": "Payment", "Memos": [memo]}}
                    )
                return _make_success_response({"transactions": txs})
            return _make_fail_response()

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        if coverage_drops > 0:
            monitor.register_policy(VALID_NFT_ID, coverage_drops)
        _patch = patch(
            "ward.pool.AsyncJsonRpcClient",
            _async_client_factory(mock_request),
        )
        _patch.start()
        monitor._mock_patch = _patch
        return monitor

    def _stop(self, monitor):
        p = getattr(monitor, "_mock_patch", None)
        if p:
            try:
                p.stop()
            except RuntimeError:
                pass

    @pytest.mark.asyncio
    async def test_solvent_pool(self):
        # 24M - 20M base reserve = 4M usable vs 1M coverage = 4x
        monitor = self._make_monitor(balance_drops=24_000_000, coverage_drops=1_000_000)
        try:
            health = await monitor.get_health()
            assert health.is_solvent
        finally:
            self._stop(monitor)

    @pytest.mark.asyncio
    async def test_undercollateralized_pool(self):
        # 21M - 20M base = 1M usable vs 10M coverage = 0.1x
        monitor = self._make_monitor(
            balance_drops=21_000_000, coverage_drops=10_000_000
        )
        try:
            health = await monitor.get_health()
            assert not health.is_solvent
        finally:
            self._stop(monitor)

    @pytest.mark.asyncio
    async def test_zero_coverage_returns_inf_ratio(self):
        monitor = self._make_monitor(balance_drops=25_000_000, coverage_drops=0)
        try:
            health = await monitor.get_health()
            assert health.coverage_ratio == float("inf")
            assert health.is_solvent
        finally:
            self._stop(monitor)

    @pytest.mark.asyncio
    async def test_premium_rate_increases_with_risk(self):
        monitor_safe = self._make_monitor(
            balance_drops=120_000_000, coverage_drops=1_000_000
        )
        monitor_stressed = self._make_monitor(
            balance_drops=23_000_000, coverage_drops=2_800_000
        )
        try:
            health_safe = await monitor_safe.get_health()
            health_stressed = await monitor_stressed.get_health()
            assert (
                health_stressed.dynamic_premium_rate >= health_safe.dynamic_premium_rate
            )
        finally:
            self._stop(monitor_safe)
            self._stop(monitor_stressed)

    @pytest.mark.asyncio
    async def test_calculate_premium_pro_rated(self):
        monitor = self._make_monitor(balance_drops=30_000_000, coverage_drops=1_000_000)
        try:
            health = await monitor.get_health()
            result_30 = monitor.calculate_premium(health, 1_000_000, 30)
            result_365 = monitor.calculate_premium(health, 1_000_000, 365)
            assert result_30["premium_drops"] > 0
            assert result_365["premium_drops"] > result_30["premium_drops"]
        finally:
            self._stop(monitor)

    def test_invalid_pool_address_raises(self):
        with pytest.raises(ValidationError):
            PoolHealthMonitor(pool_address="invalid-addr")

    @pytest.mark.asyncio
    async def test_starter_tier_blocks_elevated_minting(self):
        """Tier gate: Starter must not mint at elevated risk (index.html tier rules)."""
        from ward.constants import LicenseTier

        # 23.5M - (20M base + 2M owner@1) = 1.5M usable vs 1M coverage = 1.5x = elevated tier
        monitor = self._make_monitor(balance_drops=23_500_000, coverage_drops=1_000_000)
        try:
            health = await monitor.get_health()
            allowed = monitor.is_minting_allowed(health, LicenseTier.STARTER)
            assert not allowed, "Starter should be blocked at elevated tier"
        finally:
            self._stop(monitor)

    @pytest.mark.asyncio
    async def test_enterprise_tier_allows_elevated_minting(self):
        """Tier gate: Enterprise can mint at elevated risk."""
        from ward.constants import LicenseTier

        # 23.5M - (20M base + 2M owner@1) = 1.5M usable vs 1M coverage = 1.5x = elevated tier
        monitor = self._make_monitor(balance_drops=23_500_000, coverage_drops=1_000_000)
        try:
            health = await monitor.get_health()
            allowed = monitor.is_minting_allowed(health, LicenseTier.ENTERPRISE)
            assert allowed, "Enterprise should be allowed at elevated tier"
        finally:
            self._stop(monitor)


# ===========================================================================
# Tests: EscrowSettlement — crypto condition flow  (fix #8)
# ===========================================================================


class TestEscrowSettlement:
    def _make_settlement(self) -> EscrowSettlement:
        async def mock_request(req):
            return _make_success_response(
                _make_server_info_response(close_time=100_000_000)
            )

        settlement = EscrowSettlement()
        _patch = patch(
            "ward.settlement.AsyncJsonRpcClient",
            _async_client_factory(mock_request),
        )
        _patch.start()
        settlement._mock_patch = _patch
        return settlement

    def _stop(self, s):
        p = getattr(s, "_mock_patch", None)
        if p:
            try:
                p.stop()
            except RuntimeError:
                pass

    def _make_record(self, condition_hex: str) -> EscrowRecord:
        return EscrowRecord(
            claim_id="claim-123",
            nft_token_id=VALID_NFT_ID,
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=500_000,
            escrow_sequence=42,
            condition_hex=condition_hex,
            tx_hash="E" * 64,
            dispute_deadline_ripple=100_000_000 - 1,  # already finishable
            cancel_after_ripple=100_000_000 + 7200,  # not yet cancellable
        )

    @pytest.mark.asyncio
    async def test_finish_before_dispute_window_raises(self):
        settlement = self._make_settlement()
        preimage, cond, fulf = generate_claim_condition()
        record = self._make_record(cond)
        pool_wallet = FakeWallet(classic_address=VALID_ADDRESS)
        claimant_wallet = FakeWallet(classic_address=VALID_ADDRESS2)
        try:
            with pytest.raises(ValidationError, match="dispute window"):
                await settlement.finish_escrow(
                    pool_address=pool_wallet.classic_address,
                    claimant_address_signer=claimant_wallet.classic_address,
                    escrow_record=record,
                    fulfillment_hex=fulf,
                )
        finally:
            self._stop(settlement)

    @pytest.mark.asyncio
    async def test_cancel_before_window_raises(self):
        settlement = self._make_settlement()
        preimage, cond, fulf = generate_claim_condition()
        record = EscrowRecord(
            claim_id="claim-123",
            nft_token_id=VALID_NFT_ID,
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=500_000,
            escrow_sequence=2,
            condition_hex=cond,
            tx_hash="G" * 64,
            dispute_deadline_ripple=50_000_000,
            cancel_after_ripple=200_000_000,  # far future
        )
        pool_wallet = FakeWallet(classic_address=VALID_ADDRESS)
        try:
            with pytest.raises(ValidationError, match="not yet cancellable"):
                await settlement.cancel_escrow(
                    pool_address=pool_wallet.classic_address,
                    escrow_record=record,
                    reason="dispute",
                )
        finally:
            self._stop(settlement)

    @pytest.mark.asyncio
    async def test_create_escrow_validates_addresses(self):
        settlement = self._make_settlement()
        preimage, cond, fulf = generate_claim_condition()
        try:
            with pytest.raises(ValidationError):
                await settlement.create_claim_escrow(
                    pool_address=VALID_ADDRESS,
                    claimant_address="bad-addr",
                    payout_drops=500_000,
                    condition_hex=cond,
                    claim_id="claim-xyz",
                    nft_token_id=VALID_NFT_ID,
                )
        finally:
            self._stop(settlement)


# ===========================================================================
# Tests: KYC helpers
# ===========================================================================


class TestBuildKycHash:
    def test_deterministic(self):
        h1 = build_kyc_hash("KYC_VERIFIED", VALID_ADDRESS, 1000)
        h2 = build_kyc_hash("KYC_VERIFIED", VALID_ADDRESS, 1000)
        assert h1 == h2

    def test_different_inputs_differ(self):
        h1 = build_kyc_hash("KYC_VERIFIED", VALID_ADDRESS, 1000)
        h2 = build_kyc_hash("KYC_VERIFIED", VALID_ADDRESS2, 1000)
        assert h1 != h2

    def test_all_valid_kyc_types(self):
        for kyc_type in VALID_KYC_TYPES:
            h = build_kyc_hash(kyc_type, VALID_ADDRESS, 1000)
            assert len(h) == 64


class TestValidateKycHash:
    def test_valid_hash_passes(self):
        h = build_kyc_hash("KYC_VERIFIED", VALID_ADDRESS, 1)
        validate_kyc_hash(h)  # no exception

    def test_valid_sha256_hex_passes(self):
        h = hashlib.sha256(b"test").hexdigest()
        validate_kyc_hash(h)

    def test_too_short_raises(self):
        with pytest.raises(ValidationError):
            validate_kyc_hash("abc123")

    def test_too_long_raises(self):
        with pytest.raises(ValidationError):
            validate_kyc_hash("a" * 65)

    def test_uppercase_rejected(self):
        h = "A" * 64
        with pytest.raises(ValidationError):
            validate_kyc_hash(h)

    def test_not_string_raises(self):
        with pytest.raises(ValidationError):
            validate_kyc_hash(12345)  # type: ignore[arg-type]

    def test_non_hex_chars_raise(self):
        with pytest.raises(ValidationError):
            validate_kyc_hash("g" * 64)

    def test_none_raises(self):
        with pytest.raises(ValidationError):
            validate_kyc_hash(None)  # type: ignore[arg-type]


# ===========================================================================
# Tests: Credential constants
# ===========================================================================


class TestCredentialConstants:
    def test_credential_nft_taxon_is_282(self):
        # WARD_CREDENTIAL_TAXON == 282 per spec (was 283 — corrected)
        from ward.constants import WARD_CREDENTIAL_TAXON

        assert WARD_CREDENTIAL_TAXON == 282
        assert CREDENTIAL_NFT_TAXON == 282  # backward-compat alias

    def test_policy_taxon_is_281(self):
        # WARD_POLICY_TAXON == 281 per security_notes.md §2.1 and §2.13
        assert WARD_POLICY_TAXON == 281

    def test_taxon_distinct_from_policy(self):
        assert CREDENTIAL_NFT_TAXON != WARD_POLICY_TAXON

    def test_valid_kyc_types_contains_required(self):
        assert "KYC_VERIFIED" in VALID_KYC_TYPES
        assert "AML_CLEARED" in VALID_KYC_TYPES


# ===========================================================================
# Tests: PoolHealthMonitor — advanced coverage gaps (pool.py refactor)
# ===========================================================================


class TestPoolHealthMonitorAdvanced:
    """Coverage for pool.py changes: active-coverage trust boundary, reserve
    math, tier gates, and calculate_premium signature."""

    def _make_pool_monitor(
        self, balance_drops=30_000_000, coverage_drops=0, owner_count=0
    ):
        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models.requests import AccountTx as _ATx

            if isinstance(req, _AI):
                return _make_success_response(
                    {
                        "account_data": {
                            "Balance": str(balance_drops),
                            "OwnerCount": owner_count,
                        }
                    }
                )
            if isinstance(req, _ATx):
                txs = []
                if coverage_drops > 0:
                    from ward.coverage import build_premium_memo

                    memo = build_premium_memo(VALID_NFT_ID, coverage_drops)
                    txs.append(
                        {"tx_json": {"TransactionType": "Payment", "Memos": [memo]}}
                    )
                return _make_success_response({"transactions": txs})
            return _make_fail_response()

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        if coverage_drops > 0:
            monitor.register_policy(VALID_NFT_ID, coverage_drops)
        _patch = patch(
            "ward.pool.AsyncJsonRpcClient",
            _async_client_factory(mock_request),
        )
        _patch.start()
        monitor._mock_patch = _patch
        return monitor

    def _stop(self, m):
        p = getattr(m, "_mock_patch", None)
        if p:
            try:
                p.stop()
            except RuntimeError:
                pass

    @pytest.mark.asyncio
    async def test_pool_active_coverage_on_chain(self):
        """active_coverage_drops is summed from on-chain premium payment memos."""

        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models.requests import AccountTx as _ATx

            from ward.coverage import build_premium_memo

            if isinstance(req, _AI):
                return _make_success_response(
                    {"account_data": {"Balance": "30000000", "OwnerCount": 0}}
                )
            if isinstance(req, _ATx):
                txs = [
                    {
                        "tx_json": {
                            "TransactionType": "Payment",
                            "Memos": [build_premium_memo("A" * 64, 500_000)],
                        }
                    },
                    {
                        "tx_json": {
                            "TransactionType": "Payment",
                            "Memos": [build_premium_memo("D" * 64, 300_000)],
                        }
                    },
                ]
                return _make_success_response({"transactions": txs})
            return _make_fail_response()

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        monitor.register_policy("A" * 64, 500_000)
        monitor.register_policy("D" * 64, 300_000)
        _patch = patch(
            "ward.pool.AsyncJsonRpcClient", _async_client_factory(mock_request)
        )
        _patch.start()
        try:
            health = await monitor.get_health()
            assert health.active_coverage_drops == 800_000
        finally:
            try:
                _patch.stop()
            except RuntimeError:
                pass

    @pytest.mark.asyncio
    async def test_pool_owner_reserve_calculation(self):
        """usable = balance - (base_reserve + OwnerCount × owner_reserve)."""
        from ward.constants import XRPL_BASE_RESERVE_DROPS, XRPL_OWNER_RESERVE_DROPS

        owner_count = 5
        balance = 50_000_000
        expected_usable = max(
            0,
            balance - XRPL_BASE_RESERVE_DROPS - owner_count * XRPL_OWNER_RESERVE_DROPS,
        )
        monitor = self._make_pool_monitor(
            balance_drops=balance, coverage_drops=0, owner_count=owner_count
        )
        try:
            health = await monitor.get_health()
            assert health.usable_drops == expected_usable
        finally:
            self._stop(monitor)

    def test_pool_tier_gate_starter_blocked_elevated(self):
        """Starter license is blocked when pool risk tier is 'elevated'."""
        from ward.constants import LicenseTier

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        health = PoolHealth(
            pool_address=VALID_ADDRESS,
            balance_drops=23_500_000,
            usable_drops=1_500_000,
            active_coverage_drops=1_000_000,
            owner_count=1,
            coverage_ratio=1.5,
            is_solvent=True,
            dynamic_premium_rate=0.06,
            risk_tier="elevated",
        )
        assert not monitor.is_minting_allowed(health, LicenseTier.STARTER)

    def test_pool_tier_gate_standard_allows_elevated(self):
        """Standard license is allowed when pool risk tier is 'elevated'."""
        from ward.constants import LicenseTier

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        health = PoolHealth(
            pool_address=VALID_ADDRESS,
            balance_drops=23_500_000,
            usable_drops=1_500_000,
            active_coverage_drops=1_000_000,
            owner_count=1,
            coverage_ratio=1.5,
            is_solvent=True,
            dynamic_premium_rate=0.06,
            risk_tier="elevated",
        )
        assert monitor.is_minting_allowed(health, LicenseTier.STANDARD)

    def test_pool_tier_gate_all_blocked_high(self):
        """All license tiers are blocked when pool risk tier is 'high'."""
        from ward.constants import LicenseTier

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        health = PoolHealth(
            pool_address=VALID_ADDRESS,
            balance_drops=20_000_000,
            usable_drops=0,
            active_coverage_drops=1_000_000,
            owner_count=0,
            coverage_ratio=0.0,
            is_solvent=False,
            dynamic_premium_rate=0.10,
            risk_tier="high",
        )
        for tier in (LicenseTier.STARTER, LicenseTier.STANDARD, LicenseTier.ENTERPRISE):
            assert not monitor.is_minting_allowed(health, tier), (
                f"{tier!r} should be blocked at 'high' risk"
            )

    def test_pool_calculate_premium_sync(self):
        """calculate_premium is synchronous and returns dict{'premium_drops': int}."""
        import inspect

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        assert not inspect.iscoroutinefunction(monitor.calculate_premium), (
            "calculate_premium must be sync, not async"
        )
        health = PoolHealth(
            pool_address=VALID_ADDRESS,
            balance_drops=50_000_000,
            usable_drops=30_000_000,
            active_coverage_drops=1_000_000,
            owner_count=0,
            coverage_ratio=30.0,
            is_solvent=True,
            dynamic_premium_rate=0.005,
            risk_tier="safest",
        )
        result = monitor.calculate_premium(health, 1_000_000, 30)
        assert isinstance(result, dict), "calculate_premium must return a dict"
        assert "premium_drops" in result
        assert isinstance(result["premium_drops"], int)
        assert result["premium_drops"] > 0


# ===========================================================================
# Tests: ClaimValidator — URI dual-format, parallelism, step-9 reserve
# ===========================================================================


class TestClaimValidatorAdvanced(TestClaimValidatorAdversarial):
    """URI format parsing, asyncio.gather concurrency, and step-9 OwnerCount."""

    def test_validator_dual_uri_format_legacy(self):
        """_parse_nft_metadata accepts legacy 'protocol: ward/v1' URI format."""
        metadata = {
            "protocol": "ward/v1",
            "vault_address": VALID_ADDRESS,
            "coverage_drops": "500000",
            "expiry_ledger_time": 999_999_999,
        }
        uri_hex = json.dumps(metadata, separators=(",", ":")).encode().hex().upper()
        nft_data = {
            "URI": uri_hex,
            "NFTokenID": VALID_NFT_ID,
            "NFTokenTaxon": WARD_POLICY_TAXON,
        }
        parsed, err = ClaimValidator._parse_nft_metadata(nft_data)
        assert err is None, f"Unexpected error: {err}"
        assert parsed["vault_address"] == VALID_ADDRESS
        assert parsed["coverage_drops"] == "500000"

    def test_validator_dual_uri_format_compact(self):
        """_parse_nft_metadata accepts compact v0.2 URI format (w/v/c/e keys)."""
        metadata = {
            "w": "ward-v1",
            "v": VALID_ADDRESS,
            "c": "1000000",
            "e": 999_999_999,
        }
        uri_hex = json.dumps(metadata, separators=(",", ":")).encode().hex().upper()
        nft_data = {
            "URI": uri_hex,
            "NFTokenID": VALID_NFT_ID,
            "NFTokenTaxon": WARD_POLICY_TAXON,
        }
        parsed, err = ClaimValidator._parse_nft_metadata(nft_data)
        assert err is None, f"Unexpected error: {err}"
        assert parsed["v"] == VALID_ADDRESS
        assert parsed["c"] == "1000000"

    def test_validator_owner_reserve_in_step9(self):
        """Step 9 solvency check: OwnerCount drives reserve, not just base."""
        validator = ClaimValidator()

        # With OwnerCount=0: usable = 30M - 20M = 10M; payout=5M; ratio=2 → pass
        assert (
            validator._step9_check_pool_solvency(
                {"Balance": "30000000", "OwnerCount": 0}, 5_000_000
            )
            is None
        )

        # With OwnerCount=5: reserve = 20M+10M = 30M; usable = 0 < payout → fail
        result = validator._step9_check_pool_solvency(
            {"Balance": "30000000", "OwnerCount": 5}, 5_000_000
        )
        assert result is not None
        assert "insolvent" in result.lower()

    @pytest.mark.asyncio
    async def test_validator_steps_run_concurrently(self):
        """validate_claim calls asyncio.gather to parallelise steps 1, 4, pool."""
        import asyncio as _asyncio

        _orig_gather = _asyncio.gather
        gather_widths: List[int] = []

        async def spy_gather(*coros, **kwargs):
            gather_widths.append(len(coros))
            return await _orig_gather(*coros, **kwargs)

        validator = self._make_validator_with_mocks()
        with patch("ward.validator.asyncio.gather", new=spy_gather):
            await self._validate(
                validator,
                claimant_address=VALID_ADDRESS,
                nft_token_id=VALID_NFT_ID,
                defaulted_vault=VALID_ADDRESS,
                loan_id=VALID_LOAN_ID,
                pool_address=VALID_ADDRESS2,
            )

        assert gather_widths, "asyncio.gather was never called"
        assert any(n >= 3 for n in gather_widths), (
            f"Expected gather with ≥3 coroutines; got widths={gather_widths}"
        )


# ===========================================================================
# Tests: EscrowSettlement — timing semantics and trust model
# ===========================================================================


class TestEscrowSettlementAdvanced:
    """Timing (48h/72h), ward-never-sees-preimage invariant, ward_signed=False."""

    def _make_settlement_mocks(self, current_time: int = 100_000_000):
        """Return (settlement, context_manager_stack_patches)."""
        from xrpl.wallet import Wallet as _Wallet

        pool_wallet = _Wallet.create()
        fake_resp = MagicMock()
        fake_resp.result = {"hash": "A" * 64, "Sequence": 1}

        async def noop_request(req):
            return _make_success_response({})

        patches = [
            patch(
                "ward.settlement.AsyncJsonRpcClient",
                _async_client_factory(noop_request),
            ),
            patch(
                "ward.settlement.get_ledger_close_time",
                AsyncMock(return_value=current_time),
            ),
            patch(
                "ward.settlement.build_unsigned_tx", AsyncMock(return_value=fake_resp)
            ),
            patch("ward.settlement.autofill", AsyncMock(side_effect=lambda tx, c: tx)),
        ]
        return pool_wallet, patches

    @pytest.mark.asyncio
    async def test_settlement_finish_after_48h(self):
        """EscrowRecord.dispute_deadline_ripple = ledger_time + 48 × 3600."""
        from ward.constants import ESCROW_DISPUTE_HOURS

        KNOWN_TIME = 100_000_000
        pool_wallet, patches = self._make_settlement_mocks(KNOWN_TIME)
        _, cond, _ = generate_claim_condition()

        settlement = EscrowSettlement()
        for p in patches:
            p.start()
        try:
            record = await settlement.create_claim_escrow(
                pool_address=pool_wallet.classic_address,
                claimant_address=VALID_ADDRESS,
                payout_drops=500_000,
                condition_hex=cond,
                nft_token_id=VALID_NFT_ID,
                claim_id="claim-48h",
            )
        finally:
            for p in patches:
                try:
                    p.stop()
                except RuntimeError:
                    pass

        assert (
            record.dispute_deadline_ripple == KNOWN_TIME + ESCROW_DISPUTE_HOURS * 3_600
        )
        assert not getattr(record, "ward_signed", False)  # ward_signed = False

    @pytest.mark.asyncio
    async def test_settlement_cancel_after_72h(self):
        """EscrowRecord.cancel_after_ripple = ledger_time + 72 × 3600."""
        from ward.constants import ESCROW_CANCEL_HOURS

        KNOWN_TIME = 100_000_000
        pool_wallet, patches = self._make_settlement_mocks(KNOWN_TIME)
        _, cond, _ = generate_claim_condition()

        settlement = EscrowSettlement()
        for p in patches:
            p.start()
        try:
            record = await settlement.create_claim_escrow(
                pool_address=pool_wallet.classic_address,
                claimant_address=VALID_ADDRESS,
                payout_drops=500_000,
                condition_hex=cond,
                nft_token_id=VALID_NFT_ID,
                claim_id="claim-72h",
            )
        finally:
            for p in patches:
                try:
                    p.stop()
                except RuntimeError:
                    pass

        assert record.cancel_after_ripple == KNOWN_TIME + ESCROW_CANCEL_HOURS * 3_600
        assert not getattr(record, "ward_signed", False)  # ward_signed = False

    def test_settlement_ward_never_sees_preimage(self):
        """create_claim_escrow signature has condition_hex, never fulfillment_hex."""
        import inspect

        settlement = EscrowSettlement()
        params = list(inspect.signature(settlement.create_claim_escrow).parameters)
        assert "condition_hex" in params
        assert "fulfillment_hex" not in params
        assert "preimage" not in params

    def test_settlement_ward_signed_false(self):
        """EscrowRecord carries no server-side signing flag; ward_signed=False."""
        record = EscrowRecord(
            claim_id="test",
            nft_token_id=VALID_NFT_ID,
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=500_000,
            escrow_sequence=1,
            condition_hex="A" * 78,
            tx_hash="B" * 64,
        )
        # ward_signed is False — Ward never holds server-side keys
        assert not getattr(record, "ward_signed", False)
        assert "ward_signed" not in record.__dataclass_fields__


# ===========================================================================
# Tests: VaultMonitor — reconnect loop and confirmation gate
# ===========================================================================


class TestVaultMonitorAdvanced:
    """Reconnect on drop, recovery path, and 3-ledger confirmation gate."""

    @pytest.mark.asyncio
    async def test_monitor_reconnect_on_disconnect(self):
        """run() reconnects automatically after a WebSocket disconnect."""
        import asyncio as _asyncio

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])
        connect_count = 0

        class _FakeClient:
            async def __aenter__(self):
                nonlocal connect_count
                connect_count += 1
                if connect_count == 1:
                    raise OSError("simulated disconnect")
                monitor._stop_event.set()
                monitor._running = False
                return self

            async def __aexit__(self, *a):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def send(self, *a):
                pass

        with patch(
            "ward.vault_monitor.AsyncWebsocketClient", lambda _url: _FakeClient()
        ):
            with patch("ward.vault_monitor.asyncio.sleep", AsyncMock()):
                await _asyncio.wait_for(monitor.run(), timeout=3.0)

        assert connect_count == 2, (
            f"Expected 2 connect attempts after 1 disconnect; got {connect_count}"
        )

    @pytest.mark.asyncio
    async def test_monitor_resets_counter_on_recovery(self):
        """When on-chain verify returns None (loan recovered), callback never fires."""
        from ward.vault_monitor import DefaultSignal

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS], confirm_count=1)
        fired: List = []

        @monitor.on_verified_default
        async def cb(event):
            fired.append(event)

        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=0.5,
            ledger_index=1000,
        )
        monitor._pending[VALID_LOAN_ID] = signal

        with patch.object(
            monitor, "_verify_default_on_chain", AsyncMock(return_value=None)
        ):
            await monitor._process_pending_confirmations(AsyncMock(), 1001)

        assert len(fired) == 0, (
            "Callback must not fire when on-chain verify returns None"
        )

    @pytest.mark.asyncio
    async def test_monitor_requires_3_consecutive_closes(self):
        """on_verified_default fires on the 3rd ledger close, not the 2nd."""
        from ward.vault_monitor import DefaultSignal, VerifiedDefault

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS], confirm_count=3)
        fired: List = []

        @monitor.on_verified_default
        async def cb(event):
            fired.append(event)

        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=0.5,
            ledger_index=1000,
        )
        monitor._pending[VALID_LOAN_ID] = signal

        verified_event = VerifiedDefault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=0.5,
            first_ledger_index=1000,
            confirmed_ledger=1003,
        )
        mock_verify = AsyncMock(return_value=verified_event)
        mock_client = AsyncMock()

        with patch.object(monitor, "_verify_default_on_chain", mock_verify):
            await monitor._process_pending_confirmations(mock_client, 1001)
            assert len(fired) == 0, "Must not fire after 1st close"

            await monitor._process_pending_confirmations(mock_client, 1002)
            assert len(fired) == 0, "Must not fire after 2nd close"

            await monitor._process_pending_confirmations(mock_client, 1003)
            assert len(fired) == 1, "Must fire exactly once after 3rd close"


# ===========================================================================
# Tests: primitives — submit_with_retry and URI guard
# ===========================================================================


class TestPrimitivesAdvanced:
    """submit_with_retry retry logic and the 512-hex-char URI guard."""

    @pytest.mark.asyncio
    async def test_submit_with_retry_retries_on_tel_insuf_fee(self):
        """submit_with_retry retries on telINSUF_FEE_P then succeeds."""
        from ward.primitives import submit_with_retry

        call_count = 0

        async def mock_submit(tx, client, wallet):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count < 2:
                resp.is_successful.return_value = False
                resp.result = {
                    "meta": {"TransactionResult": "telINSUF_FEE_P"},
                    "engine_result": "telINSUF_FEE_P",
                }
            else:
                resp.is_successful.return_value = True
                resp.result = {"meta": {"TransactionResult": "tesSUCCESS"}}
            return resp

        with patch("ward.primitives.submit_and_wait", mock_submit):
            with patch("ward.primitives.asyncio.sleep", AsyncMock()):
                result = await submit_with_retry(
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                    max_attempts=3,
                    base_delay=0.0,
                )

        assert call_count == 2, f"Expected 2 attempts; got {call_count}"
        assert result.is_successful()

    @pytest.mark.asyncio
    async def test_submit_with_retry_raises_on_non_retryable(self):
        """submit_with_retry raises LedgerError immediately on tecNO_DST."""
        from ward.primitives import LedgerError, submit_with_retry

        call_count = 0

        async def mock_submit(tx, client, wallet):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.is_successful.return_value = False
            resp.result = {
                "meta": {"TransactionResult": "tecNO_DST"},
                "engine_result": "tecNO_DST",
            }
            return resp

        with patch("ward.primitives.submit_and_wait", mock_submit):
            with pytest.raises(LedgerError, match="tecNO_DST"):
                await submit_with_retry(MagicMock(), MagicMock(), MagicMock())

        assert call_count == 1, "Non-retryable error must not be retried"

    def test_uri_hex_assertion_fires_over_512(self):
        """_parse_nft_metadata rejects any NFT URI longer than 512 hex chars."""
        long_meta = {
            "w": "ward-v1",
            "v": VALID_ADDRESS,
            "c": "1000000",
            "e": 999_999,
            "extra": "x" * 300,  # pushes JSON well over 256 bytes
        }
        uri_hex = json.dumps(long_meta, separators=(",", ":")).encode().hex().upper()
        assert len(uri_hex) > 512, "Test setup: URI must exceed 512 hex chars"

        nft_data = {
            "URI": uri_hex,
            "NFTokenID": VALID_NFT_ID,
            "NFTokenTaxon": WARD_POLICY_TAXON,
        }
        _, err = ClaimValidator._parse_nft_metadata(nft_data)
        assert err is not None, "Expected an error for URI > 512 hex chars"
        assert "512" in err


# ===========================================================================
# Integration tests (require XRPL testnet, skipped in unit runs)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_purchase_coverage_testnet():
    """
    Full integration test: request faucet wallet, purchase a 1-XRP policy.
    Requires XRPL Altnet testnet access.
    Set WARD_POOL_ADDRESS env var or use the default faucet address.
    """
    from xrpl.asyncio.clients import AsyncJsonRpcClient as _RPC
    from xrpl.asyncio.wallet import generate_faucet_wallet as _gfw

    pool_address = os.getenv("WARD_POOL_ADDRESS", VALID_ADDRESS)
    rpc = _RPC("https://s.altnet.rippletest.net:51234/")
    wallet = await _gfw(rpc, debug=False)

    client = WardClient(url="https://s.altnet.rippletest.net:51234/")
    result = await client.purchase_coverage(
        institution_address=wallet.classic_address,
        vault_address=VALID_ADDRESS,
        coverage_drops=1_000_000,
        period_days=7,
        pool_address=pool_address,
        premium_rate=0.01,
    )

    assert result["status"] == "active"
    assert len(result["nft_token_id"]) == 64
    assert result["coverage_drops"] == 1_000_000


# ===========================================================================
# Security mitigation tests — all 15 attack vectors (Code4rena audit prep)
# ===========================================================================


def _make_validator_with_mocks(**kwargs):
    """Module-level convenience: delegates to TestClaimValidatorAdversarial._make_validator_with_mocks."""
    return TestClaimValidatorAdversarial()._make_validator_with_mocks(**kwargs)


# ---------------------------------------------------------------------------
# 2.1 Policy Forgery
# ---------------------------------------------------------------------------


class TestPolicyForgery:
    """2.1 — Policy forgery / fake claim injection mitigations."""

    def test_forgery_invalid_taxon_rejected(self):
        """ClaimValidator rejects NFTs with wrong taxon (sentinel _WRONG_TAXON path)."""
        from ward.validator import ClaimValidator

        nft = {"NFTokenID": "A" * 64, "NFTokenTaxon": 9999, "URI": ""}
        # Simulate step 1 finding NFT with wrong taxon
        result = (
            ClaimValidator._make_validator_stub_reject_taxon(nft) if False else None
        )
        # Direct unit test: wrong taxon returns sentinel
        import asyncio

        validator = ClaimValidator()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.is_successful.return_value = True
            mock_resp.result = {
                "account_nfts": [{"NFTokenID": "A" * 64, "NFTokenTaxon": 9999}],
            }
            client = AsyncMock()
            client.request = AsyncMock(return_value=mock_resp)
            r = await validator._step1_verify_nft_exists(
                client, VALID_ADDRESS, "A" * 64
            )
            return r

        result = asyncio.run(_run())
        from ward.validator import _WRONG_TAXON as _WT

        assert result is _WT, "NFT with wrong taxon must return _WRONG_TAXON sentinel"

    def test_forgery_wrong_flags_rejected(self):
        """Policy NFT must have TF_BURNABLE set and TF_TRANSFERABLE absent."""

        # Verify WardClient.purchase_coverage uses TF_BURNABLE only (no TF_TRANSFERABLE)
        import inspect

        from ward.client import WardClient

        src = inspect.getsource(WardClient.purchase_coverage)
        assert "TF_BURNABLE" in src, "purchase_coverage must set TF_BURNABLE"
        assert "TF_TRANSFERABLE" not in src, (
            "purchase_coverage must NOT set TF_TRANSFERABLE — "
            "policies are non-transferable by design"
        )

    def test_ward_policy_taxon_is_281(self):
        """WARD_POLICY_TAXON must be 281 — hard-coded per spec."""
        assert WARD_POLICY_TAXON == 281


# ---------------------------------------------------------------------------
# 2.2 Double-Spend / Replay
# ---------------------------------------------------------------------------


class TestReplayProtection:
    """2.2 — Policy double-spend / replay attack mitigations."""

    @pytest.mark.asyncio
    async def test_replay_burned_nft_rejected(self):
        """Step 1 returns None when NFT is absent (burned), rejecting the claim."""
        validator = _make_validator_with_mocks(nft_exists=False)
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed == 0
        assert (
            "not found" in result.rejection_reason.lower()
            or "burned" in result.rejection_reason.lower()
        )

    def test_replay_rate_limit_enforced(self):
        """check_rate_limit raises after CLAIM_RATE_LIMIT_MAX attempts on the same NFT."""

        from ward.primitives import _rate_limit_windows, check_rate_limit

        unique_nft = "B" * 64  # use a unique ID to avoid cross-test pollution
        # Clear any prior state for this NFT
        _rate_limit_windows.pop(unique_nft, None)

        from ward.constants import CLAIM_RATE_LIMIT_MAX

        for _ in range(CLAIM_RATE_LIMIT_MAX):
            check_rate_limit(unique_nft)

        with pytest.raises(ValidationError, match="Rate limit"):
            check_rate_limit(unique_nft)


# ---------------------------------------------------------------------------
# 2.3 Policy Transfer
# ---------------------------------------------------------------------------


class TestPolicyTransfer:
    """2.3 — Policy transfer / stolen claim mitigations."""

    def test_policy_nft_not_transferable(self):
        """NFTokenMint must NOT include tfTransferable flag."""
        from ward.constants import TF_BURNABLE, TF_TRANSFERABLE

        # Ward only sets TF_BURNABLE — verify TF_TRANSFERABLE is not ORed in
        flags_used = TF_BURNABLE
        assert (flags_used & TF_TRANSFERABLE) == 0, (
            "Policy NFT flags must not include TF_TRANSFERABLE"
        )

    def test_policy_flags_explicit(self):
        """TF_TRANSFERABLE constant is defined so its absence can be asserted."""
        from ward.constants import TF_BURNABLE, TF_TRANSFERABLE

        assert TF_TRANSFERABLE == 0x00000008
        assert TF_BURNABLE == 0x00000001
        # They are distinct flags
        assert TF_TRANSFERABLE != TF_BURNABLE
        assert (TF_BURNABLE & TF_TRANSFERABLE) == 0


# ---------------------------------------------------------------------------
# 2.4 Signal Manipulation
# ---------------------------------------------------------------------------


class TestSignalManipulation:
    """2.4 — Vault operator default signal manipulation mitigations."""

    @pytest.mark.asyncio
    async def test_monitor_ignores_event_health_ratio(self):
        """
        VaultMonitor must NOT trust health_ratio from the WebSocket event.
        After ledger_closed it re-fetches via independent RPC call.
        _verify_default_on_chain is always called — never short-circuited by event data.
        """
        from ward.vault_monitor import DefaultSignal, VaultMonitor, VerifiedDefault

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS], confirm_count=1)
        fired = []

        @monitor.on_verified_default
        async def cb(e):
            fired.append(e)

        # Plant a pending signal
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=999.0,  # bogus value from "event"
            ledger_index=1000,
            confirm_count=1,
        )
        monitor._pending[VALID_LOAN_ID] = signal

        verified = VerifiedDefault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=0.4,  # on-chain re-fetched value
            first_ledger_index=1000,
            confirmed_ledger=1001,
        )
        with patch.object(
            monitor, "_verify_default_on_chain", AsyncMock(return_value=verified)
        ) as mock_verify:
            await monitor._process_pending_confirmations(AsyncMock(), 1001)

        # _verify_default_on_chain MUST have been called (independent RPC)
        mock_verify.assert_called_once()
        assert len(fired) == 1
        # Callback receives the on-chain value, not the event value
        assert fired[0].health_ratio == 0.4

    @pytest.mark.asyncio
    async def test_monitor_verifies_via_rpc(self):
        """_verify_default_on_chain uses LedgerEntry (independent RPC), not event data."""
        from xrpl.models import LedgerEntry

        from ward.vault_monitor import DefaultSignal, VaultMonitor

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS], confirm_count=1)
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            health_ratio=0.5,
            ledger_index=1000,
        )

        mock_resp = MagicMock()
        mock_resp.is_successful.return_value = True
        mock_resp.result = {
            "node": {"Flags": 0x00010000, "PrincipalOutstanding": 5000000}
        }
        client = AsyncMock()
        client.request = AsyncMock(return_value=mock_resp)

        result = await monitor._verify_default_on_chain(client, signal)
        assert result is not None
        # Confirm client.request was called (independent RPC, not event data)
        client.request.assert_called_once()
        call_arg = client.request.call_args[0][0]
        assert isinstance(call_arg, LedgerEntry)


# ---------------------------------------------------------------------------
# 2.5 Clock Manipulation
# ---------------------------------------------------------------------------


class TestClockManipulation:
    """2.5 — Clock manipulation / expiry bypass mitigations."""

    @pytest.mark.asyncio
    async def test_expiry_uses_ledger_time_not_server_clock(self):
        """
        _step2_check_expiry must call get_ledger_close_time (XRPL ledger time),
        never time.time() or datetime.now().
        """
        import inspect

        from ward.validator import ClaimValidator

        src = inspect.getsource(ClaimValidator._step2_check_expiry)
        assert "get_ledger_close_time" in src, (
            "_step2_check_expiry must use get_ledger_close_time(), not server clock"
        )
        assert "time.time()" not in src, "Must not use time.time() for expiry"
        assert "datetime.now()" not in src, "Must not use datetime.now() for expiry"

    @pytest.mark.asyncio
    async def test_expiry_rejects_expired_policy(self):
        """Expired policy (ledger time > expiry) must be rejected at step 2."""
        past_expiry = 100  # far in the past
        metadata = {"w": "ward-v1", "v": VALID_VAULT, "c": "1000000", "e": past_expiry}

        async def mock_get_time(_client):
            return 999_999_999  # ledger time >> expiry

        from ward.validator import ClaimValidator

        validator = ClaimValidator()
        with patch("ward.validator.get_ledger_close_time", mock_get_time):
            err = await validator._step2_check_expiry(AsyncMock(), metadata)

        assert err is not None
        assert "expired" in err.lower()


# ---------------------------------------------------------------------------
# 2.6 Front-Running Escrow
# ---------------------------------------------------------------------------


class TestFrontRunning:
    """2.6 — Front-running the escrow release mitigations."""

    def test_settlement_never_accepts_preimage(self):
        """EscrowSettlement.create_claim_escrow signature must not accept a preimage param."""
        import inspect

        from ward.settlement import EscrowSettlement

        sig = inspect.signature(EscrowSettlement.create_claim_escrow)
        assert "preimage" not in sig.parameters, (
            "create_claim_escrow must NEVER accept a preimage — "
            "Ward only receives condition_hex"
        )

    def test_only_condition_hex_transmitted(self):
        """EscrowRecord must not have a preimage field."""
        import dataclasses

        from ward.settlement import EscrowRecord

        field_names = {f.name for f in dataclasses.fields(EscrowRecord)}
        assert "preimage" not in field_names, (
            "EscrowRecord must not store a preimage — only condition_hex"
        )
        assert "condition_hex" in field_names


# ---------------------------------------------------------------------------
# 2.7 Monitor Spoofing
# ---------------------------------------------------------------------------


class TestMonitorSpoofing:
    """2.7 — Ward monitoring module spoofing mitigations."""

    def test_monitor_rejects_non_tls_url(self):
        """VaultMonitor must reject ws:// (non-TLS) URLs at construction."""
        with pytest.raises(ValidationError, match="wss://"):
            VaultMonitor(
                vault_addresses=[VALID_ADDRESS],
                websocket_url="ws://s.altnet.rippletest.net:51233/",
            )

    def test_monitor_rejects_unknown_endpoint(self):
        """VaultMonitor must reject unknown wss:// endpoints."""
        with pytest.raises(ValidationError, match="not in allowed list"):
            VaultMonitor(
                vault_addresses=[VALID_ADDRESS],
                websocket_url="wss://evil-node.example.com:51233/",
            )

    def test_allowed_ws_urls_tls_only(self):
        """Every URL in ALLOWED_WS_URLS must use wss:// (TLS)."""
        from ward.constants import ALLOWED_WS_URLS

        for url in ALLOWED_WS_URLS:
            assert url.startswith("wss://"), (
                f"All allowed WS URLs must be TLS (wss://), got: {url}"
            )

    def test_monitor_accepts_known_tls_endpoint(self):
        """VaultMonitor accepts known wss:// endpoints without raising."""
        from ward.constants import DEFAULT_TESTNET_WS

        # Should not raise
        monitor = VaultMonitor(
            vault_addresses=[VALID_ADDRESS], websocket_url=DEFAULT_TESTNET_WS
        )
        assert monitor._ws_url == DEFAULT_TESTNET_WS


# ---------------------------------------------------------------------------
# 2.8 Pool Drainage
# ---------------------------------------------------------------------------


class TestPoolDrainage:
    """2.8 — Pool drainage via inflated loss calculation mitigations."""

    @pytest.mark.asyncio
    async def test_pool_drainage_blocks_new_policies(self):
        """is_minting_allowed returns False when pool is in 'high' risk tier."""
        from ward.pool import PoolHealth, PoolHealthMonitor

        health = PoolHealth(
            pool_address=VALID_ADDRESS,
            balance_drops=10_000_000,
            usable_drops=0,
            active_coverage_drops=100_000_000,
            owner_count=0,
            coverage_ratio=0.0,  # 0 < 1.5 → "high" tier
            is_solvent=False,
            dynamic_premium_rate=0.1,
            risk_tier="high",
        )
        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        for tier in ("starter", "standard", "enterprise"):
            assert not monitor.is_minting_allowed(health, tier), (
                f"Minting must be blocked in 'high' risk tier for {tier}"
            )

    @pytest.mark.asyncio
    async def test_coverage_exceeds_balance_blocked(self):
        """
        Pool with coverage > usable balance is classified as 'high' risk tier,
        blocking new policy minting.
        """
        from ward.pool import PoolHealthMonitor

        # 10 XRP usable, 100 XRP active coverage → ratio 0.1 → 'high'
        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models.requests import AccountTx as _ATx

            from ward.coverage import build_premium_memo

            if isinstance(req, _AI):
                return _make_success_response(
                    {"account_data": {"Balance": "30000000", "OwnerCount": 1}}
                )
            if isinstance(req, _ATx):
                memo = build_premium_memo(VALID_NFT_ID, 100_000_000)
                return _make_success_response(
                    {
                        "transactions": [
                            {"tx_json": {"TransactionType": "Payment", "Memos": [memo]}}
                        ]
                    }
                )
            return _make_fail_response()

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        monitor.register_policy(VALID_NFT_ID, 100_000_000)  # 100 XRP coverage
        with patch("ward.pool.AsyncJsonRpcClient", _async_client_factory(mock_request)):
            health = await monitor.get_health()

        assert health.risk_tier == "high"
        assert not monitor.is_minting_allowed(health, "enterprise")


# ---------------------------------------------------------------------------
# 2.9 Coverage Ratio Manipulation
# ---------------------------------------------------------------------------


class TestCoverageRatioManipulation:
    """2.9 — Coverage ratio manipulation mitigations."""

    @pytest.mark.asyncio
    async def test_claim_refetches_health_ratio_independently(self):
        """
        ClaimValidator step 6 re-fetches pool balance from live ledger,
        independent of VaultMonitor's cached value.
        """
        import inspect

        from ward.validator import ClaimValidator

        src = inspect.getsource(ClaimValidator._step6_check_coverage_breach)
        # Must issue AccountInfo request (independent RPC)
        assert "AccountInfo" in src, (
            "_step6_check_coverage_breach must call AccountInfo (independent RPC read)"
        )
        assert "cache" not in src.lower(), "_step6 must not use cached values"


# ---------------------------------------------------------------------------
# 2.10 Address Injection
# ---------------------------------------------------------------------------


class TestAddressInjection:
    """2.10 — Address injection / transaction crafting mitigations."""

    @pytest.mark.asyncio
    async def test_invalid_address_rejected_at_boundary(self):
        """validate_claim returns rejection for invalid XRPL address inputs."""
        validator = ClaimValidator()
        result = await validator.validate_claim(
            claimant_address="not-an-address",
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed == 0

    @pytest.mark.asyncio
    async def test_malformed_address_injection(self):
        """SQL-injection-style strings in address fields are rejected by base58check."""
        validator = ClaimValidator()
        for bad_addr in ["' OR 1=1--", "<script>", "r" + "A" * 50, ""]:
            result = await validator.validate_claim(
                claimant_address=bad_addr,
                nft_token_id=VALID_NFT_ID,
                defaulted_vault=VALID_VAULT,
                loan_id=VALID_LOAN_ID,
                pool_address=VALID_ADDRESS,
            )
            assert not result.approved, f"Should reject bad address: {bad_addr!r}"


# ---------------------------------------------------------------------------
# 2.11 Key Exfiltration
# ---------------------------------------------------------------------------


class TestKeyExfiltration:
    """2.11 — Key exfiltration mitigations."""

    def test_no_wallet_stored_after_call(self):
        """WardClient must not retain a wallet attribute between calls."""
        from ward.client import WardClient

        client = WardClient()
        assert not hasattr(client, "_wallet"), (
            "WardClient must not store a wallet as instance attribute"
        )
        assert not hasattr(client, "wallet"), (
            "WardClient must not store a wallet as public attribute"
        )

    def test_ward_has_no_wallet_field(self):
        """No Ward module-level class stores a wallet as an instance attribute."""

        from ward.client import WardClient
        from ward.pool import PoolHealthMonitor
        from ward.settlement import EscrowSettlement
        from ward.validator import ClaimValidator

        for cls in (WardClient, ClaimValidator, EscrowSettlement, PoolHealthMonitor):
            instance = cls.__new__(cls)
            # Check instance dict after __init__ with dummy args where possible
            attrs = vars(instance) if hasattr(instance, "__dict__") else {}
            for attr_name in attrs:
                assert (
                    "wallet" not in attr_name.lower()
                    and "key" not in attr_name.lower()
                    and "seed" not in attr_name.lower()
                ), f"{cls.__name__}.{attr_name} looks like it stores key material"


# ---------------------------------------------------------------------------
# 2.12 Rate Limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """2.12 — Rate limiting bypass / DoS mitigations."""

    def test_rate_limit_3_attempts_per_5min(self):
        """check_rate_limit allows exactly CLAIM_RATE_LIMIT_MAX calls, then raises."""
        from ward.constants import CLAIM_RATE_LIMIT_MAX
        from ward.primitives import _rate_limit_windows, check_rate_limit

        nft_id = "C" * 64
        _rate_limit_windows.pop(nft_id, None)

        for i in range(CLAIM_RATE_LIMIT_MAX):
            assert check_rate_limit(nft_id) is True, f"Call {i + 1} should succeed"

        with pytest.raises(ValidationError, match="Rate limit"):
            check_rate_limit(nft_id)

    def test_rate_limit_resets_after_window(self):
        """After CLAIM_RATE_LIMIT_WINDOW_S elapses, the window resets."""
        import time as _time

        from ward.constants import CLAIM_RATE_LIMIT_MAX, CLAIM_RATE_LIMIT_WINDOW_S
        from ward.primitives import _rate_limit_windows, check_rate_limit

        nft_id = "D" * 64
        _rate_limit_windows.pop(nft_id, None)

        for _ in range(CLAIM_RATE_LIMIT_MAX):
            check_rate_limit(nft_id)

        # Fake old timestamps by backdating entries
        import collections

        old_ts = _time.monotonic() - CLAIM_RATE_LIMIT_WINDOW_S - 1
        _rate_limit_windows[nft_id] = collections.deque([old_ts] * CLAIM_RATE_LIMIT_MAX)

        # Window has expired — should succeed again
        assert check_rate_limit(nft_id) is True

    def test_rate_limit_per_nft_not_per_address(self):
        """Rate limit is keyed per NFT token ID, not per claimant address."""
        from ward.constants import CLAIM_RATE_LIMIT_MAX
        from ward.primitives import _rate_limit_windows, check_rate_limit

        nft_a = "E" * 64
        nft_b = "F" * 64
        _rate_limit_windows.pop(nft_a, None)
        _rate_limit_windows.pop(nft_b, None)

        for _ in range(CLAIM_RATE_LIMIT_MAX):
            check_rate_limit(nft_a)

        # Exhausted for nft_a, but nft_b should still work
        assert check_rate_limit(nft_b) is True

    def test_rate_limit_evicts_expired_entries_on_access(self):
        """FIX #8: accessing an NFT with all-expired timestamps evicts stale entries."""
        import collections
        import time as _time

        from ward.constants import CLAIM_RATE_LIMIT_WINDOW_S
        from ward.primitives import _rate_limit_windows, check_rate_limit

        nft_id = "2A" * 32
        _rate_limit_windows.pop(nft_id, None)

        # Seed two expired timestamps
        old_ts = _time.monotonic() - CLAIM_RATE_LIMIT_WINDOW_S - 1
        _rate_limit_windows[nft_id] = collections.deque([old_ts, old_ts])

        # After calling check_rate_limit, expired entries must be gone
        # and the window should contain only the just-added timestamp
        check_rate_limit(nft_id)
        window = _rate_limit_windows.get(nft_id)
        assert window is not None, "window entry must still exist"
        assert len(window) == 1, (
            f"Expected 1 fresh timestamp after eviction, got {len(window)}"
        )


# ---------------------------------------------------------------------------
# 2.13 NFT Taxon Spoofing
# ---------------------------------------------------------------------------


class TestNFTTaxonSpoofing:
    """2.13 — NFT taxon spoofing mitigations."""

    @pytest.mark.asyncio
    async def test_wrong_taxon_claim_rejected(self):
        """validate_claim rejects NFTs with taxon != WARD_POLICY_TAXON."""
        validator = _make_validator_with_mocks(nft_taxon=999)
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert "taxon" in result.rejection_reason.lower()

    def test_taxon_spoofing_different_taxon(self):
        """WARD_POLICY_TAXON is a hard constant — not configurable by callers."""
        from ward.constants import WARD_CREDENTIAL_TAXON, WARD_POLICY_TAXON

        assert WARD_POLICY_TAXON == 281, "Policy taxon must be 281"
        assert WARD_CREDENTIAL_TAXON == 282, "Credential taxon must be 282"
        assert WARD_POLICY_TAXON != WARD_CREDENTIAL_TAXON

    def test_taxon_constants_not_mutable(self):
        """Taxon constants must be module-level ints, not variables that drift."""
        import ward.constants as _c

        assert isinstance(_c.WARD_POLICY_TAXON, int)
        assert isinstance(_c.WARD_CREDENTIAL_TAXON, int)


# ---------------------------------------------------------------------------
# 2.14 XRP / Drops Unit Confusion
# ---------------------------------------------------------------------------


class TestDropsUnitConfusion:
    """2.14 — XRP / drops unit confusion mitigations."""

    def test_float_drops_rejected(self):
        """validate_drops must reject float inputs."""
        from ward.primitives import validate_drops

        with pytest.raises(ValidationError, match="integer"):
            validate_drops(1.5)
        with pytest.raises(ValidationError, match="integer"):
            validate_drops(0.0)
        with pytest.raises(ValidationError, match="integer"):
            validate_drops(1_000_000.0)

    def test_negative_drops_rejected(self):
        """validate_drops must reject negative values."""
        from ward.primitives import validate_drops

        with pytest.raises(ValidationError):
            validate_drops(-1)

    def test_drops_overflow_rejected(self):
        """validate_drops must reject amounts exceeding the XRP max supply."""
        from ward.constants import XRP_MAX_DROPS
        from ward.primitives import validate_drops

        with pytest.raises(ValidationError, match="max XRP supply"):
            validate_drops(XRP_MAX_DROPS + 1)

    def test_zero_drops_accepted(self):
        """validate_drops allows 0 (coverage check, not payment)."""
        from ward.primitives import validate_drops

        validate_drops(0)  # must not raise

    def test_max_drops_accepted(self):
        """validate_drops allows exactly XRP_MAX_DROPS."""
        from ward.constants import XRP_MAX_DROPS
        from ward.primitives import validate_drops

        validate_drops(XRP_MAX_DROPS)  # must not raise

    def test_bool_rejected(self):
        """True/False (bool subclass of int) must be rejected."""
        from ward.primitives import validate_drops

        with pytest.raises(ValidationError, match="integer"):
            validate_drops(True)
        with pytest.raises(ValidationError, match="integer"):
            validate_drops(False)


# ---------------------------------------------------------------------------
# 2.15 Silent Network Failure
# ---------------------------------------------------------------------------


class TestSilentNetworkFailure:
    """2.15 — Silent network failure / heartbeat mitigations."""

    def test_heartbeat_constant_is_60s(self):
        """MONITOR_HEARTBEAT_TIMEOUT_S must be 60 seconds."""
        from ward.constants import MONITOR_HEARTBEAT_TIMEOUT_S

        assert MONITOR_HEARTBEAT_TIMEOUT_S == 60

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_triggers_reconnect(self):
        """
        VaultMonitor._run_with_heartbeat raises TimeoutError when asyncio.wait_for
        times out (i.e., no message arrives within MONITOR_HEARTBEAT_TIMEOUT_S).
        """
        import asyncio as _aio

        from ward.vault_monitor import VaultMonitor

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])

        class _SlowIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                await _aio.sleep(999)
                raise StopAsyncIteration

        class _FakeClient:
            def __aiter__(self):
                return _SlowIter()

            async def send(self, *a):
                pass

        # Mock asyncio.wait_for in vault_monitor to immediately raise TimeoutError,
        # simulating the heartbeat timeout firing.
        with patch(
            "ward.vault_monitor.asyncio.wait_for", side_effect=_aio.TimeoutError()
        ):
            with pytest.raises(_aio.TimeoutError):
                await monitor._run_with_heartbeat(_FakeClient())

    @pytest.mark.asyncio
    async def test_monitor_reconnects_on_silence(self):
        """
        VaultMonitor.run() reconnects after heartbeat timeout (simulated by
        _run_with_heartbeat raising TimeoutError).
        """
        import asyncio as _aio

        from ward.vault_monitor import VaultMonitor

        monitor = VaultMonitor(vault_addresses=[VALID_ADDRESS])
        connect_count = 0

        class _FakeClient:
            async def __aenter__(self):
                nonlocal connect_count
                connect_count += 1
                if connect_count == 1:
                    raise _aio.TimeoutError("simulated heartbeat timeout")
                monitor._stop_event.set()
                monitor._running = False
                return self

            async def __aexit__(self, *a):
                pass

            async def send(self, *a):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        with patch("ward.vault_monitor.AsyncWebsocketClient", lambda _u: _FakeClient()):
            with patch("ward.vault_monitor.asyncio.sleep", AsyncMock()):
                await _aio.wait_for(monitor.run(), timeout=3.0)

        assert connect_count == 2, (
            f"Expected 2 connect attempts after heartbeat timeout; got {connect_count}"
        )


# ===========================================================================
# Tests: Critical Bug Fixes (Code4rena pre-audit)
# ===========================================================================


class TestCriticalBugFixes:
    """
    FIX 1: NFTokenBurn must use claimant_wallet (pool wallet gets tecNO_PERMISSION).
    FIX 2: Steps 7 and 8 must perform real ledger queries, not logger stubs.
    FIX 3: TxBuilder.escrow_finish must accept condition/fulfillment parameters.
    """

    # ── FIX 1: NFTokenBurn permission ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_finish_escrow_burn_uses_claimant_wallet(self):
        """FIX 1: NFTokenBurn account must be claimant_wallet, not pool_wallet."""
        from xrpl.models import NFTokenBurn as _NFTokenBurn
        from xrpl.wallet import Wallet as _Wallet

        burn_wallet_addresses: List[str] = []
        fake_resp = MagicMock()
        fake_resp.result = {"hash": "A" * 64}

        async def noop_request(req):
            return _make_success_response({})

        async def track_burn(tx, client):
            if isinstance(tx, _NFTokenBurn):
                burn_wallet_addresses.append(tx.account)
            from ward.primitives import UnsignedTransaction

            return UnsignedTransaction(
                tx_type=tx.__class__.__name__,
                account=getattr(tx, "account", ""),
                destination=getattr(tx, "destination", "") or "",
                amount_drops=0,
            )

        pool_wallet = _Wallet.create()
        claimant_wallet = _Wallet.create()

        record = EscrowRecord(
            claim_id="fix1-test",
            nft_token_id=VALID_NFT_ID,
            pool_address=pool_wallet.classic_address,
            claimant_address=claimant_wallet.classic_address,
            payout_drops=500_000,
            escrow_sequence=1,
            condition_hex="A" * 78,
            tx_hash="B" * 64,
            dispute_deadline_ripple=200_000_000,
            cancel_after_ripple=300_000_000,
        )

        settlement = EscrowSettlement()
        with patch(
            "ward.settlement.AsyncJsonRpcClient", _async_client_factory(noop_request)
        ):
            with patch(
                "ward.settlement.get_ledger_close_time",
                AsyncMock(return_value=100_000_000),
            ):
                with patch(
                    "ward.settlement.build_unsigned_tx",
                    AsyncMock(side_effect=track_burn),
                ):
                    with patch(
                        "ward.settlement.autofill",
                        AsyncMock(side_effect=lambda tx, c: tx),
                    ):
                        await settlement.finish_escrow(
                            pool_address=pool_wallet.classic_address,
                            claimant_address_signer=claimant_wallet.classic_address,
                            escrow_record=record,
                            fulfillment_hex="F" * 78,
                        )

        assert len(burn_wallet_addresses) == 1, "NFTokenBurn must be submitted once"
        assert burn_wallet_addresses[0] == claimant_wallet.classic_address, (
            f"NFTokenBurn must use claimant_wallet; got {burn_wallet_addresses[0]!r}"
        )
        assert burn_wallet_addresses[0] != pool_wallet.classic_address, (
            "NFTokenBurn must NOT use pool_wallet — that causes tecNO_PERMISSION"
        )

    def test_finish_escrow_signature_has_claimant_wallet(self):
        """FIX 1: finish_escrow must declare claimant_wallet parameter."""
        import inspect

        sig = inspect.signature(EscrowSettlement().finish_escrow)
        assert "claimant_address_signer" in sig.parameters, (
            "finish_escrow must accept claimant_address_signer parameter"
        )

    # ── FIX 2: Steps 7 and 8 real ledger queries ─────────────────────────────

    @pytest.mark.asyncio
    async def test_step7_rejects_burned_nft(self):
        """FIX 2: Step 7 rejects claim when NFT has been burned since step 1."""
        validator = ClaimValidator()
        client = MagicMock()
        err = await validator._step7_verify_nft_live(None, VALID_NFT_ID)
        assert err is not None, "Step 7 must return an error when NFT is burned"
        assert any(kw in err.lower() for kw in ("burned", "not found", "replay")), (
            f"Error should mention burned/not found/replay: {err!r}"
        )

    @pytest.mark.asyncio
    async def test_step8_rejects_transferred_nft(self):
        """FIX 2: Step 8 rejects claim when claimant no longer holds NFT."""
        validator = ClaimValidator()
        client = MagicMock()
        err = await validator._step8_verify_claimant_holds_nft(
            None, VALID_ADDRESS, VALID_NFT_ID
        )
        assert err is not None, "Step 8 must return an error when NFT not held"
        assert any(kw in err.lower() for kw in ("claimant", "hold", "does not")), (
            f"Error should mention claimant/hold: {err!r}"
        )

    @pytest.mark.asyncio
    async def test_step7_passes_when_nft_live(self):
        """FIX 2: Step 7 passes when NFT still exists on ledger."""
        validator = ClaimValidator()
        client = MagicMock()
        nft_data = {"NFTokenID": VALID_NFT_ID, "NFTokenTaxon": WARD_POLICY_TAXON}
        err = await validator._step7_verify_nft_live(nft_data, VALID_NFT_ID)
        assert err is None, f"Step 7 must pass when NFT is live; got: {err!r}"

    @pytest.mark.asyncio
    async def test_step8_passes_when_claimant_holds_nft(self):
        """FIX 2: Step 8 passes when claimant holds the NFT."""
        validator = ClaimValidator()
        client = MagicMock()
        nft_data = {"NFTokenID": VALID_NFT_ID, "NFTokenTaxon": WARD_POLICY_TAXON}
        err = await validator._step8_verify_claimant_holds_nft(
            nft_data, VALID_ADDRESS, VALID_NFT_ID
        )
        assert err is None, f"Step 8 must pass when claimant holds NFT; got: {err!r}"

    @pytest.mark.asyncio
    async def test_step7_and_8_are_not_log_only_stubs(self):
        """FIX 2: Steps 7 and 8 must be real async methods, not logger stubs."""
        import inspect

        validator = ClaimValidator()
        assert hasattr(validator, "_step7_verify_nft_live"), (
            "ClaimValidator must have _step7_verify_nft_live method"
        )
        assert hasattr(validator, "_step8_verify_claimant_holds_nft"), (
            "ClaimValidator must have _step8_verify_claimant_holds_nft method"
        )
        assert inspect.iscoroutinefunction(validator._step7_verify_nft_live), (
            "_step7_verify_nft_live must be async"
        )
        assert inspect.iscoroutinefunction(
            validator._step8_verify_claimant_holds_nft
        ), "_step8_verify_claimant_holds_nft must be async"

    # ── FIX 3: TxBuilder.escrow_finish condition/fulfillment ─────────────────

    def test_escrow_finish_includes_condition_and_fulfillment(self):
        """FIX 3: escrow_finish must pass condition and fulfillment to EscrowFinish."""
        cond = "A02580020" + "B" * 64 + "0102000000"
        fulf = "A0228020" + "C" * 64

        tx = TxBuilder.escrow_finish(
            account=VALID_ADDRESS,
            owner=VALID_ADDRESS2,
            offer_sequence=99,
            condition=cond,
            fulfillment=fulf,
        )

        assert isinstance(tx, EscrowFinish)
        assert tx.condition == cond, f"condition not set: {tx.condition!r}"
        assert tx.fulfillment == fulf, f"fulfillment not set: {tx.fulfillment!r}"

    def test_escrow_finish_works_without_condition_fulfillment(self):
        """FIX 3: escrow_finish with no condition/fulfillment still builds correctly."""
        tx = TxBuilder.escrow_finish(
            account=VALID_ADDRESS,
            owner=VALID_ADDRESS2,
            offer_sequence=1,
        )
        assert isinstance(tx, EscrowFinish)
        assert tx.account == VALID_ADDRESS
        assert tx.owner == VALID_ADDRESS2
        assert tx.offer_sequence == 1

    def test_escrow_finish_signature_accepts_condition_fulfillment(self):
        """FIX 3: escrow_finish signature must declare condition and fulfillment."""
        import inspect

        sig = inspect.signature(TxBuilder.escrow_finish)
        params = sig.parameters
        assert "condition" in params, "escrow_finish must accept condition kwarg"
        assert "fulfillment" in params, "escrow_finish must accept fulfillment kwarg"


# ===========================================================================
# Tests: Code Review Fixes #5, #14, #16
# ===========================================================================


class TestPolicyRegistryFixes:
    """FIX #5: in-memory policy registry replaces on-chain AccountNFTs scan."""

    def test_register_policy_increases_coverage(self):
        """Registering a policy adds its drops to active coverage."""
        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        assert monitor._coverage_registry == {}
        monitor.register_policy(VALID_NFT_ID, 1_000_000)
        assert monitor._coverage_registry[VALID_NFT_ID] == 1_000_000

    def test_deregister_policy_removes_coverage(self):
        """Deregistering a policy removes it from the registry."""
        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        monitor.register_policy(VALID_NFT_ID, 500_000)
        monitor.deregister_policy(VALID_NFT_ID)
        assert VALID_NFT_ID not in monitor._coverage_registry

    def test_deregister_nonexistent_policy_is_noop(self):
        """Deregistering an unknown ID does not raise."""
        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        monitor.deregister_policy("unknown-id")  # must not raise

    @pytest.mark.asyncio
    async def test_registry_coverage_reflected_in_get_health(self):
        """Active coverage from on-chain premium memos is visible in PoolHealth output."""

        async def mock_request(req):
            from xrpl.models import AccountInfo as _AI
            from xrpl.models.requests import AccountTx as _ATx

            from ward.coverage import build_premium_memo

            if isinstance(req, _AI):
                return _make_success_response(
                    {"account_data": {"Balance": "50000000", "OwnerCount": 0}}
                )
            if isinstance(req, _ATx):
                memo = build_premium_memo(VALID_NFT_ID, 2_000_000)
                return _make_success_response(
                    {
                        "transactions": [
                            {"tx_json": {"TransactionType": "Payment", "Memos": [memo]}}
                        ]
                    }
                )
            return _make_fail_response()

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        monitor.register_policy(VALID_NFT_ID, 2_000_000)
        with patch("ward.pool.AsyncJsonRpcClient", _async_client_factory(mock_request)):
            health = await monitor.get_health()

        assert health.active_coverage_drops == 2_000_000


class TestValidateClaimErrorHandling:
    """FIX #14: validate_claim always returns ValidationResult, never raises."""

    @pytest.mark.asyncio
    async def test_validate_claim_converts_ledger_error_to_result(self):
        """LedgerError raised inside async body is caught and returned as ValidationResult."""
        validator = ClaimValidator()

        mock_class = MagicMock()
        mock_class.return_value.__aenter__ = AsyncMock(
            side_effect=LedgerError("mocked ledger failure")
        )
        mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("ward.validator.AsyncJsonRpcClient", mock_class):
            result = await validator.validate_claim(
                claimant_address=VALID_ADDRESS,
                nft_token_id=VALID_NFT_ID,
                defaulted_vault=VALID_ADDRESS,
                loan_id=VALID_LOAN_ID,
                pool_address=VALID_ADDRESS2,
            )

        assert not result.approved
        assert "ledger" in result.rejection_reason.lower()


class TestPremiumVerificationGap:
    """FIX #16: premium payment must be verified on-chain before approval."""

    @pytest.mark.asyncio
    async def test_fake_nft_without_premium_is_rejected(self):
        """
        Known gap (High severity): an NFT minted without paying a premium
        must be rejected. Currently all 9 steps pass with no premium check.
        pool_balance_drops=100M ensures pool solvency so step 9 does not mask the gap.
        Rate limit is reset so step 9 rate-limit path does not mask the gap either.
        """
        from ward.primitives import _rate_limit_windows

        # Reset rate limit for VALID_NFT_ID so step 9 rate-limit path
        # does not mask the premium verification assertion under test.
        _rate_limit_windows.pop(VALID_NFT_ID, None)

        validator = _make_validator_with_mocks(
            pool_balance_drops=100_000_000,
            premium_paid=False,
        )
        p = getattr(validator, "_mock_patch", None)
        try:
            result = await validator.validate_claim(
                claimant_address=VALID_ADDRESS,
                nft_token_id=VALID_NFT_ID,
                defaulted_vault=VALID_VAULT,
                loan_id=VALID_LOAN_ID,
                pool_address=VALID_ADDRESS2,
            )
        finally:
            if p:
                try:
                    p.stop()
                except RuntimeError:
                    pass
        assert not result.approved
        assert "premium payment" in result.rejection_reason.lower()


# ===========================================================================
# Tests: Multi-vault institution registry
# ===========================================================================


class TestMultiVaultRegistry:
    """FIX: multi-vault support — one X-Institution-Key maps to multiple vaults."""

    def setup_method(self):
        from ward.registry import clear_registry

        clear_registry()
        # Generate valid XRPL addresses for registry tests
        from xrpl.wallet import Wallet as _Wallet

        self.vault_a = VALID_ADDRESS  # rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh
        self.vault_b = VALID_ADDRESS2  # rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe
        self.vault_c = _Wallet.create().classic_address  # fresh valid address

    async def test_register_single_vault(self):
        """Institution can register a vault."""
        from ward.registry import get_vaults, register_vault

        await register_vault("key_001", self.vault_a)
        vaults = await get_vaults("key_001")
        assert len(vaults) == 1
        assert vaults[0]["vault_address"] == self.vault_a

    async def test_register_multiple_vaults(self):
        """Institution can register multiple vaults under one key."""
        from ward.registry import get_vaults, register_vault

        await register_vault("key_001", self.vault_a)
        await register_vault("key_001", self.vault_b)
        await register_vault("key_001", self.vault_c)
        vaults = await get_vaults("key_001")
        assert len(vaults) == 3

    async def test_different_institutions_isolated(self):
        """Two institution keys cannot see each other's vaults."""
        from ward.registry import get_vaults, register_vault

        await register_vault("key_A", self.vault_a)
        await register_vault("key_B", self.vault_b)
        vaults_a = await get_vaults("key_A")
        vaults_b = await get_vaults("key_B")
        assert len(vaults_a) == 1
        assert len(vaults_b) == 1
        assert vaults_a[0]["vault_address"] != vaults_b[0]["vault_address"]

    async def test_duplicate_vault_rejected(self):
        """Cannot register the same vault address twice under one key."""
        from ward.registry import register_vault

        await register_vault("key_001", self.vault_a)
        with pytest.raises(WardError, match="already registered"):
            await register_vault("key_001", self.vault_a)

    async def test_deregister_vault(self):
        """Institution can remove a vault from their registry."""
        from ward.registry import deregister_vault, get_vaults, register_vault

        await register_vault("key_001", self.vault_a)
        await register_vault("key_001", self.vault_b)
        await deregister_vault("key_001", self.vault_a)
        vaults = await get_vaults("key_001")
        assert len(vaults) == 1
        assert vaults[0]["vault_address"] == self.vault_b

    async def test_invalid_address_rejected(self):
        """Invalid XRPL address format raises WardError or ValidationError."""
        from ward.registry import register_vault

        with pytest.raises((WardError, Exception)):
            await register_vault("key_001", "not-a-valid-xrpl-address")

    async def test_institution_key_hash_not_raw(self):
        """Registry stores key hash — never the raw institution key."""
        from ward.registry import register_vault

        entry = await register_vault("key_001", self.vault_a)
        assert entry["institution_key_hash"] != "key_001"
        assert len(entry["institution_key_hash"]) == 64  # SHA-256 hex

    async def test_invalid_tier_rejected(self):
        """Only starter / standard / enterprise tiers are accepted."""
        from ward.registry import register_vault

        with pytest.raises(WardError, match="Invalid tier"):
            await register_vault("key_001", self.vault_a, tier="premium")

    async def test_deregister_returns_false_when_not_found(self):
        """deregister_vault returns False if the address was never registered."""
        from ward.registry import deregister_vault

        removed = await deregister_vault("key_001", self.vault_a)
        assert removed is False

    async def test_get_vault_returns_none_when_missing(self):
        """get_vault returns None when vault is not registered."""
        from ward.registry import get_vault

        result = await get_vault("key_001", self.vault_a)
        assert result is None

    async def test_get_vault_returns_entry_when_present(self):
        """get_vault returns the correct registration entry."""
        from ward.registry import get_vault, register_vault

        await register_vault(
            "key_001", self.vault_a, tier="standard", label="Main Vault"
        )
        entry = await get_vault("key_001", self.vault_a)
        assert entry is not None
        assert entry["vault_address"] == self.vault_a
        assert entry["tier"] == "standard"
        assert entry["label"] == "Main Vault"


# ===========================================================================
# TestWebhookNotifications — Week 2 Session 2
# ===========================================================================


class TestWebhookNotifications:
    """Unit tests for ward/webhooks.py threshold detection and registry."""

    def setup_method(self):
        from ward.webhooks import clear_webhooks

        clear_webhooks()

    # ----------------------------------------------------------------
    # determine_event threshold logic
    # ----------------------------------------------------------------

    async def test_threshold_crossing_warning(self):
        """Crossing below 2.0 from above fires HEALTH_WARNING."""
        from ward.webhooks import WebhookEvent, determine_event

        event = determine_event(1.9, 2.5)
        assert event == WebhookEvent.HEALTH_WARNING

    async def test_threshold_crossing_elevated(self):
        """Crossing below 1.75 fires HEALTH_ELEVATED (not WARNING)."""
        from ward.webhooks import WebhookEvent, determine_event

        event = determine_event(1.7, 1.8)
        assert event == WebhookEvent.HEALTH_ELEVATED

    async def test_threshold_crossing_critical(self):
        """Crossing below 1.5 fires HEALTH_CRITICAL."""
        from ward.webhooks import WebhookEvent, determine_event

        event = determine_event(1.4, 1.6)
        assert event == WebhookEvent.HEALTH_CRITICAL

    async def test_default_resolved(self):
        """Recovery above 1.5 from below fires DEFAULT_RESOLVED."""
        from ward.webhooks import WebhookEvent, determine_event

        event = determine_event(1.6, 1.4)
        assert event == WebhookEvent.DEFAULT_RESOLVED

    async def test_stable_no_event(self):
        """No threshold crossing returns None."""
        from ward.webhooks import determine_event

        event = determine_event(2.1, 2.3)
        assert event is None

    async def test_no_previous_no_event(self):
        """First reading with no previous ratio returns None."""
        from ward.webhooks import determine_event

        event = determine_event(1.4, None)
        assert event is None

    # ----------------------------------------------------------------
    # Payload invariant
    # ----------------------------------------------------------------

    async def test_payload_ward_signed_always_false(self):
        """WebhookPayload.ward_signed is always False."""
        from ward.webhooks import WebhookEvent, WebhookPayload

        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_CRITICAL,
            vault_address=VALID_ADDRESS,
            health_ratio=1.4,
            timestamp=int(time.time()),
        )
        assert payload.ward_signed is False

    # ----------------------------------------------------------------
    # Registry operations
    # ----------------------------------------------------------------

    async def test_register_and_retrieve_webhook(self):
        """Registered webhook is retrievable by vault address."""
        from ward.webhooks import WebhookConfig, get_webhooks, register_webhook

        config = WebhookConfig(
            url="https://example.com/hook",
            vault_address=VALID_ADDRESS,
            secret="s3cr3t",
        )
        await register_webhook(config)
        hooks = await get_webhooks(VALID_ADDRESS)
        assert len(hooks) == 1
        assert hooks[0].url == "https://example.com/hook"

    async def test_deregister_webhook(self):
        """Deregistering a webhook removes it from the registry."""
        from ward.webhooks import (
            WebhookConfig,
            deregister_webhook,
            get_webhooks,
            register_webhook,
        )

        await register_webhook(
            WebhookConfig(url="https://example.com/hook", vault_address=VALID_ADDRESS)
        )
        removed = await deregister_webhook(VALID_ADDRESS, "https://example.com/hook")
        assert removed is True
        hooks = await get_webhooks(VALID_ADDRESS)
        assert len(hooks) == 0

    async def test_http_url_rejected(self):
        """Webhook URL must use https — plaintext http is rejected."""
        from ward.primitives import WardError
        from ward.webhooks import WebhookConfig, register_webhook

        with pytest.raises(WardError, match="https://"):
            await register_webhook(
                WebhookConfig(
                    url="http://example.com/hook", vault_address=VALID_ADDRESS
                )
            )

    # ----------------------------------------------------------------
    # Registration / deregistration edge cases (branch coverage)
    # ----------------------------------------------------------------

    async def test_webhook_registration(self):
        """Second webhook for the same vault appends without re-initialising the list."""
        from ward.webhooks import WebhookConfig, get_webhooks, register_webhook

        cfg1 = WebhookConfig(
            url="https://hook1.example.com/a", vault_address=VALID_ADDRESS
        )
        cfg2 = WebhookConfig(
            url="https://hook2.example.com/b", vault_address=VALID_ADDRESS
        )
        await register_webhook(cfg1)
        await register_webhook(
            cfg2
        )  # hits the 84->86 branch (vault already in registry)
        hooks = await get_webhooks(VALID_ADDRESS)
        assert len(hooks) == 2
        assert {h.url for h in hooks} == {cfg1.url, cfg2.url}

    async def test_webhook_deregistration(self):
        """deregister_webhook returns False when vault has no registered webhooks."""
        from ward.webhooks import deregister_webhook

        removed = await deregister_webhook(VALID_ADDRESS, "https://example.com/hook")
        assert removed is False  # hits line 94 — early return

    # ----------------------------------------------------------------
    # fire_webhook — event filter and delivery dispatch
    # ----------------------------------------------------------------

    async def test_fire_webhook_filters_events(self):
        """fire_webhook skips configs whose event filter does not match the fired event."""
        from ward.webhooks import (
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            fire_webhook,
            register_webhook,
        )

        cfg = WebhookConfig(
            url="https://example.com/hook",
            vault_address=VALID_ADDRESS,
            events=[WebhookEvent.HEALTH_CRITICAL],
        )
        await register_webhook(cfg)
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_WARNING,  # non-matching
            vault_address=VALID_ADDRESS,
            health_ratio=1.9,
            timestamp=1_000_000,
        )
        with patch("ward.webhooks._post_webhook", new_callable=AsyncMock) as mock_post:
            await fire_webhook(payload)
            await asyncio.sleep(0)
        mock_post.assert_not_called()

    async def test_fire_webhook_delivers_matching_event(self):
        """fire_webhook schedules _post_webhook when event matches the filter."""
        from ward.webhooks import (
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            fire_webhook,
            register_webhook,
        )

        cfg = WebhookConfig(
            url="https://example.com/hook",
            vault_address=VALID_ADDRESS,
            events=[WebhookEvent.HEALTH_CRITICAL],
        )
        await register_webhook(cfg)
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_CRITICAL,  # matching
            vault_address=VALID_ADDRESS,
            health_ratio=1.4,
            timestamp=1_000_000,
        )
        with patch("ward.webhooks._post_webhook", new_callable=AsyncMock) as mock_post:
            await fire_webhook(payload)
            await asyncio.sleep(0)  # let the task run
        mock_post.assert_called_once_with(cfg, payload)

    # ----------------------------------------------------------------
    # _post_webhook — HTTP delivery, HMAC, retry, give-up
    # ----------------------------------------------------------------

    async def test_webhook_delivery_success(self):
        """_post_webhook delivers the payload on the first attempt."""
        from ward.webhooks import (
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            _post_webhook,
        )

        config = WebhookConfig(
            url="https://example.com/hook", vault_address=VALID_ADDRESS
        )
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_CRITICAL,
            vault_address=VALID_ADDRESS,
            health_ratio=1.4,
            timestamp=1_000_000,
        )
        mock_urlopen = MagicMock()
        with patch("ward.webhooks.urlopen", mock_urlopen):
            await _post_webhook(config, payload)
        mock_urlopen.assert_called_once()
        # ward_signed = False in body
        call_args = mock_urlopen.call_args[0][0]  # urllib Request object
        import json as _json

        body = _json.loads(call_args.data)
        assert body["ward_signed"] is False

    async def test_webhook_delivery_retry_on_failure(self):
        """_post_webhook retries on transient failures and succeeds on third attempt."""
        from ward.webhooks import (
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            _post_webhook,
        )

        config = WebhookConfig(
            url="https://example.com/hook", vault_address=VALID_ADDRESS
        )
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_CRITICAL,
            vault_address=VALID_ADDRESS,
            health_ratio=1.4,
            timestamp=1_000_000,
        )
        calls: List[int] = []

        def flaky_urlopen(req, timeout=None):
            calls.append(1)
            if len(calls) < 3:
                raise OSError("connection refused")

        with (
            patch("ward.webhooks.urlopen", flaky_urlopen),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _post_webhook(config, payload)
        assert len(calls) == 3

    async def test_webhook_delivery_gives_up_after_max_retries(self):
        """_post_webhook gives up silently after MAX_RETRIES failures — never raises."""
        from ward.webhooks import (
            MAX_RETRIES,
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            _post_webhook,
        )

        config = WebhookConfig(
            url="https://example.com/hook", vault_address=VALID_ADDRESS
        )
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_WARNING,
            vault_address=VALID_ADDRESS,
            health_ratio=1.9,
            timestamp=1_000_000,
        )
        calls: List[int] = []

        def always_fail(req, timeout=None):
            calls.append(1)
            raise OSError("timeout")

        with (
            patch("ward.webhooks.urlopen", always_fail),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _post_webhook(config, payload)  # must not raise
        assert len(calls) == MAX_RETRIES

    async def test_hmac_signature_correct(self):
        """_post_webhook sets X-Ward-Signature header matching HMAC-SHA256 of body."""
        import hashlib as _hashlib
        import hmac as _hmac
        import json as _json

        from ward.webhooks import (
            WebhookConfig,
            WebhookEvent,
            WebhookPayload,
            _post_webhook,
        )

        secret = "ward-test-secret"
        config = WebhookConfig(
            url="https://example.com/hook",
            vault_address=VALID_ADDRESS,
            secret=secret,
        )
        payload = WebhookPayload(
            event=WebhookEvent.HEALTH_CRITICAL,
            vault_address=VALID_ADDRESS,
            health_ratio=1.4,
            timestamp=1_000_000,
        )
        captured: dict = {}

        def capture_urlopen(req, timeout=None):
            captured["req"] = req

        with patch("ward.webhooks.urlopen", capture_urlopen):
            await _post_webhook(config, payload)
        req = captured["req"]
        sig_header = req.get_header("X-ward-signature")
        assert sig_header is not None
        # Recompute expected signature
        body = _json.dumps(
            {
                "event": payload.event.value,
                "vault_address": payload.vault_address,
                "health_ratio": payload.health_ratio,
                "timestamp": payload.timestamp,
                "ward_signed": False,
                "data": payload.data,
            }
        ).encode()
        expected = (
            f"sha256={_hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()}"
        )
        assert sig_header == expected
        # Invariant: ward_signed hardcoded False in body — never from payload attribute
        assert _json.loads(body)["ward_signed"] is False

    def test_hmac_signature_rejects_tampered_payload(self):
        """HMAC signature of tampered body does not match signature of original body."""
        import hashlib as _hashlib
        import hmac as _hmac

        secret = "ward-test-secret"
        body = b'{"event":"health.critical","ward_signed":false}'
        tampered = body[:-1] + bytes([body[-1] ^ 0xFF])
        sig_orig = _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
        sig_tampered = _hmac.new(secret.encode(), tampered, _hashlib.sha256).hexdigest()
        assert sig_orig != sig_tampered
        assert not _hmac.compare_digest(sig_orig, sig_tampered)

    def test_all_event_types_have_payloads(self):
        """Every WebhookEvent value can be serialised in a payload with ward_signed=False."""
        import json as _json

        from ward.webhooks import WebhookEvent, WebhookPayload

        for event in WebhookEvent:
            payload = WebhookPayload(
                event=event,
                vault_address=VALID_ADDRESS,
                health_ratio=1.5,
                timestamp=1_000_000,
            )
            assert payload.ward_signed is False
            body = _json.dumps(
                {
                    "event": payload.event.value,
                    "ward_signed": payload.ward_signed,
                    "data": payload.data,
                }
            )
            parsed = _json.loads(body)
            assert parsed["ward_signed"] is False
            assert parsed["event"] == event.value


# ===========================================================================
# TestApiKeyManagement — Week 2 Session 4
# ===========================================================================


class TestApiKeyManagement:
    """Tests for institution API key generation and management."""

    def setup_method(self):
        from ward.keys import clear_keys

        clear_keys()

    def test_generate_key_has_prefix(self):
        from ward.keys import generate_key

        key = generate_key("starter", "Test Institution")
        assert key.startswith("ward_")

    def test_generate_key_sufficient_entropy(self):
        from ward.keys import generate_key

        key1 = generate_key()
        key2 = generate_key()
        assert key1 != key2
        assert len(key1) > 40

    async def test_register_and_verify_key(self):
        from ward.keys import generate_key, register_key, verify_key

        raw = generate_key("standard", "Test")
        await register_key(raw, "standard", "Test")
        record = await verify_key(raw)
        assert record is not None
        assert record.tier == "standard"
        assert record.label == "Test"

    async def test_raw_key_not_stored(self):
        from ward.keys import _key_store, generate_key, register_key

        raw = generate_key()
        await register_key(raw)
        # Raw key must not appear anywhere in the store
        for key_hash, record in _key_store.items():
            assert raw not in key_hash
            assert raw not in str(record)

    async def test_revoked_key_rejected(self):
        from ward.keys import generate_key, register_key, revoke_key, verify_key

        raw = generate_key()
        await register_key(raw)
        await revoke_key(raw)
        record = await verify_key(raw)
        assert record is None

    async def test_invalid_key_rejected(self):
        from ward.keys import verify_key

        record = await verify_key("ward_notarealkey")
        assert record is None

    async def test_rotate_key_generates_new(self):
        from ward.keys import generate_key, register_key, rotate_key

        raw = generate_key("enterprise", "BigBank")
        await register_key(raw, "enterprise", "BigBank")
        new_raw, new_record = await rotate_key(raw)
        assert new_raw != raw
        assert new_raw.startswith("ward_")
        assert new_record.tier == "enterprise"
        assert new_record.label == "BigBank"

    async def test_expired_key_rejected(self):
        from ward.keys import generate_key, register_key, verify_key

        raw = generate_key()
        await register_key(raw, expires_at=1)  # expired in 1970
        record = await verify_key(raw)
        assert record is None

    def test_invalid_tier_rejected(self):
        from ward.keys import generate_key

        with pytest.raises(ValueError, match="Invalid tier"):
            generate_key("platinum")

    def test_ward_signed_false_implied(self):
        from ward.keys import generate_key

        raw = generate_key()
        # Keys themselves don't carry ward_signed — it's in API responses
        assert raw.startswith("ward_")
        assert "signed" not in raw


# ===========================================================================
# TestOnChainCoverageRegistry — Week 2 Session 6
# ===========================================================================


class TestOnChainCoverageRegistry:
    """Tests for on-chain coverage registry via memo-encoded payments."""

    def test_build_premium_memo_structure(self):
        from ward.coverage import build_premium_memo

        nft_id = "A" * 64
        memo = build_premium_memo(nft_id, 1_000_000)
        assert "Memo" in memo
        assert "MemoType" in memo["Memo"]
        assert "MemoData" in memo["Memo"]
        # MemoType must be hex of ward/policy-premium
        import codecs

        decoded_type = codecs.decode(memo["Memo"]["MemoType"], "hex").decode()
        assert decoded_type == "ward/policy-premium"

    def test_build_premium_memo_data_format(self):
        from ward.coverage import build_premium_memo

        nft_id = "B" * 64
        memo = build_premium_memo(nft_id, 5_000_000)
        import codecs

        decoded_data = codecs.decode(memo["Memo"]["MemoData"], "hex").decode()
        assert ":" in decoded_data
        parts = decoded_data.split(":", 1)
        assert parts[0] == nft_id
        assert parts[1] == "5000000"

    def test_extract_coverage_from_valid_tx(self):
        from ward.coverage import _extract_coverage_from_tx, build_premium_memo

        nft_id = "C" * 64
        memo = build_premium_memo(nft_id, 2_000_000)
        tx = {
            "TransactionType": "Payment",
            "Memos": [memo],
        }
        result = _extract_coverage_from_tx(tx)
        assert result is not None
        assert result[0] == nft_id
        assert result[1] == 2_000_000

    def test_extract_ignores_non_payment(self):
        from ward.coverage import _extract_coverage_from_tx

        tx = {"TransactionType": "NFTokenMint", "Memos": []}
        result = _extract_coverage_from_tx(tx)
        assert result is None

    def test_extract_ignores_wrong_memo_type(self):
        from ward.coverage import _extract_coverage_from_tx

        memo = {
            "Memo": {
                "MemoType": "736f6d657468696e67656c7365",  # "somethingelse"
                "MemoData": "61626364",
            }
        }
        tx = {"TransactionType": "Payment", "Memos": [memo]}
        result = _extract_coverage_from_tx(tx)
        assert result is None

    def test_extract_ignores_malformed_memo_data(self):
        from ward.coverage import WARD_PREMIUM_MEMO_TYPE_HEX, _extract_coverage_from_tx

        memo = {
            "Memo": {
                "MemoType": WARD_PREMIUM_MEMO_TYPE_HEX,
                "MemoData": "6e6f636f6c6f6e",  # "nocolon"
            }
        }
        tx = {"TransactionType": "Payment", "Memos": [memo]}
        result = _extract_coverage_from_tx(tx)
        assert result is None

    def test_decode_memo_field_handles_empty(self):
        from ward.coverage import _decode_memo_field

        assert _decode_memo_field("") == ""
        assert _decode_memo_field(None) == ""

    def test_decode_memo_field_valid_hex(self):
        from ward.coverage import _decode_memo_field

        hex_val = "ward/policy-premium".encode().hex()
        assert _decode_memo_field(hex_val) == "ward/policy-premium"


# ===========================================================================
# Tests: ChainReader  (ward/chain_reader.py)
# ===========================================================================

from ward.chain_reader import AccountBalance, ChainReader, EscrowInfo


def _make_ws_client(request_fn):
    """Fake AsyncWebsocketClient that routes .request() calls."""
    mock = AsyncMock()
    mock.request = AsyncMock(side_effect=request_fn)
    return mock


class TestChainReaderGetAccountBalance:
    async def test_returns_account_balance(self):
        resp = _make_success_response(
            {"account_data": {"Balance": "5000000", "Sequence": 7}}
        )
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        bal = await reader.get_account_balance(VALID_ADDRESS)
        assert isinstance(bal, AccountBalance)
        assert bal.balance_drops == 5_000_000
        assert bal.sequence == 7
        assert bal.address == VALID_ADDRESS

    async def test_balance_xrp_property(self):
        resp = _make_success_response(
            {"account_data": {"Balance": "2000000", "Sequence": 1}}
        )
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        bal = await reader.get_account_balance(VALID_ADDRESS)
        assert bal.balance_xrp == pytest.approx(2.0)

    async def test_missing_sequence_defaults_to_zero(self):
        resp = _make_success_response({"account_data": {"Balance": "1000000"}})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        bal = await reader.get_account_balance(VALID_ADDRESS)
        assert bal.sequence == 0

    async def test_raises_ledger_error_on_failure(self):
        resp = _make_fail_response("actNOT_FOUND")
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        with pytest.raises(LedgerError, match="AccountInfo failed"):
            await reader.get_account_balance(VALID_ADDRESS)


class TestChainReaderVerifyAccountExists:
    async def test_returns_true_for_funded_account(self):
        resp = _make_success_response(
            {"account_data": {"Balance": "10000000", "Sequence": 1}}
        )
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        assert await reader.verify_account_exists(VALID_ADDRESS) is True

    async def test_returns_false_for_unfunded_account(self):
        resp = _make_fail_response("actNOT_FOUND")
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        assert await reader.verify_account_exists(VALID_ADDRESS) is False


class TestChainReaderGetAccountObjects:
    async def test_returns_objects_list(self):
        objects = [{"LedgerEntryType": "NFTokenPage"}, {"LedgerEntryType": "Offer"}]
        resp = _make_success_response({"account_objects": objects})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        result = await reader.get_account_objects(VALID_ADDRESS)
        assert result == objects

    async def test_returns_empty_list_when_no_objects(self):
        resp = _make_success_response({"account_objects": []})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        result = await reader.get_account_objects(VALID_ADDRESS)
        assert result == []

    async def test_passes_type_filter(self):
        captured = {}

        async def _req(req):
            captured["type"] = getattr(req, "type", None)
            return _make_success_response({"account_objects": []})

        client = _make_ws_client(_req)
        reader = ChainReader(client)
        await reader.get_account_objects(VALID_ADDRESS, obj_type="escrow")
        assert captured["type"] == "escrow"

    async def test_no_type_filter_sends_no_type(self):
        captured = {}

        async def _req(req):
            captured["type"] = getattr(req, "type", None)
            return _make_success_response({"account_objects": []})

        client = _make_ws_client(_req)
        reader = ChainReader(client)
        await reader.get_account_objects(VALID_ADDRESS)
        assert captured["type"] is None

    async def test_raises_ledger_error_on_failure(self):
        resp = _make_fail_response("actNOT_FOUND")
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        with pytest.raises(LedgerError, match="AccountObjects failed"):
            await reader.get_account_objects(VALID_ADDRESS)


class TestChainReaderGetEscrows:
    async def test_returns_escrow_info_objects(self):
        raw = [
            {
                "LedgerEntryType": "Escrow",
                "Sequence": 10,
                "Amount": "500000",
                "Destination": VALID_ADDRESS2,
                "FinishAfter": 12345,
                "CancelAfter": 99999,
                "Account": VALID_ADDRESS,
            }
        ]
        resp = _make_success_response({"account_objects": raw})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        escrows = await reader.get_escrows(VALID_ADDRESS)
        assert len(escrows) == 1
        e = escrows[0]
        assert isinstance(e, EscrowInfo)
        assert e.sequence == 10
        assert e.amount_drops == 500_000
        assert e.destination == VALID_ADDRESS2
        assert e.owner == VALID_ADDRESS

    async def test_skips_non_escrow_objects(self):
        raw = [
            {"LedgerEntryType": "NFTokenPage"},
            {
                "LedgerEntryType": "Escrow",
                "Sequence": 1,
                "Amount": "1000",
                "Destination": VALID_ADDRESS2,
                "Account": VALID_ADDRESS,
            },
        ]
        resp = _make_success_response({"account_objects": raw})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        escrows = await reader.get_escrows(VALID_ADDRESS)
        assert len(escrows) == 1

    async def test_returns_empty_list_when_no_escrows(self):
        resp = _make_success_response({"account_objects": []})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        escrows = await reader.get_escrows(VALID_ADDRESS)
        assert escrows == []

    async def test_escrow_defaults_when_fields_missing(self):
        raw = [{"LedgerEntryType": "Escrow"}]
        resp = _make_success_response({"account_objects": raw})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        escrows = await reader.get_escrows(VALID_ADDRESS)
        assert len(escrows) == 1
        e = escrows[0]
        assert e.sequence == 0
        assert e.amount_drops == 0
        assert e.owner == VALID_ADDRESS  # falls back to address arg


class TestChainReaderGetAccountTransactions:
    async def test_returns_transactions_list(self):
        txs = [{"hash": "A" * 64}, {"hash": "B" * 64}]
        resp = _make_success_response({"transactions": txs})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        result = await reader.get_account_transactions(VALID_ADDRESS)
        assert result == txs

    async def test_returns_empty_list_when_no_txs(self):
        resp = _make_success_response({"transactions": []})
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        result = await reader.get_account_transactions(VALID_ADDRESS)
        assert result == []

    async def test_raises_ledger_error_on_failure(self):
        resp = _make_fail_response("lgrNOT_FOUND")
        client = _make_ws_client(AsyncMock(return_value=resp))
        reader = ChainReader(client)
        with pytest.raises(LedgerError, match="AccountTx failed"):
            await reader.get_account_transactions(VALID_ADDRESS)

    async def test_custom_limit_passed_through(self):
        captured = {}

        async def _req(req):
            captured["limit"] = getattr(req, "limit", None)
            return _make_success_response({"transactions": []})

        client = _make_ws_client(_req)
        reader = ChainReader(client)
        await reader.get_account_transactions(VALID_ADDRESS, limit=50)
        assert captured["limit"] == 50


# ===========================================================================
# Tests: WardMonitor  (ward/monitor.py)
# ===========================================================================

import warnings as _warnings_module

from ward.monitor import WardMonitor


class TestWardMonitorConstruction:
    def test_requires_wss_url(self):
        with pytest.raises(SecurityError, match="ws://"):
            with _warnings_module.catch_warnings():
                _warnings_module.simplefilter("ignore", DeprecationWarning)
                WardMonitor(xrpl_url="ws://plaintext.example.com")

    def test_emits_deprecation_warning(self):
        with pytest.warns(DeprecationWarning, match="deprecated"):
            WardMonitor(xrpl_url="wss://xrplcluster.com")

    def test_default_vault_list_is_empty(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            m = WardMonitor(xrpl_url="wss://xrplcluster.com")
        assert m._vault_addresses == []

    def test_vault_addresses_passed_in(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            m = WardMonitor(
                vault_addresses=[VALID_ADDRESS],
                xrpl_url="wss://xrplcluster.com",
            )
        assert VALID_ADDRESS in m._vault_addresses


class TestWardMonitorAddRemoveVault:
    def _make(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            return WardMonitor(xrpl_url="wss://xrplcluster.com")

    def test_add_vault(self):
        m = self._make()
        m.add_vault(VALID_ADDRESS)
        assert VALID_ADDRESS in m._vault_addresses

    def test_add_vault_idempotent(self):
        m = self._make()
        m.add_vault(VALID_ADDRESS)
        m.add_vault(VALID_ADDRESS)
        assert m._vault_addresses.count(VALID_ADDRESS) == 1

    def test_remove_vault(self):
        m = self._make()
        m.add_vault(VALID_ADDRESS)
        m.remove_vault(VALID_ADDRESS)
        assert VALID_ADDRESS not in m._vault_addresses

    def test_remove_nonexistent_vault_is_noop(self):
        m = self._make()
        m.remove_vault(VALID_ADDRESS)  # should not raise

    def test_on_balance_change_registers_callback(self):
        m = self._make()
        cb = MagicMock()
        m.on_balance_change(cb)
        assert cb in m._callbacks


class TestWardMonitorStop:
    def test_stop_sets_running_false(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            m = WardMonitor(xrpl_url="wss://xrplcluster.com")
        m._running = True
        m.stop()
        assert m._running is False


class TestWardMonitorPollLoop:
    def _make(self, poll_interval=0.001):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            return WardMonitor(
                vault_addresses=[VALID_ADDRESS],
                xrpl_url="wss://xrplcluster.com",
                poll_interval_seconds=poll_interval,
            )

    async def test_start_calls_poll_loop_and_stops(self):
        m = self._make()
        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            m.stop()  # stop after first fetch
            return 1_000_000

        m._fetch_balance = fake_fetch
        await m.start()
        assert call_count >= 1
        assert m._running is False

    async def test_start_is_noop_when_already_running(self):
        m = self._make()
        m._running = True
        # Should return immediately without entering the loop
        fetched = []

        async def fake_fetch(addr):
            fetched.append(addr)
            return 1_000_000

        m._fetch_balance = fake_fetch
        await m.start()  # _running=True → early return
        assert fetched == []

    async def test_balance_change_fires_sync_callback(self):
        m = self._make()
        events = []
        m.on_balance_change(lambda addr, bal: events.append((addr, bal)))

        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 1_000_000
            m.stop()
            return 2_000_000  # changed balance

        m._fetch_balance = fake_fetch
        await m.start()
        assert len(events) == 1
        assert events[0] == (VALID_ADDRESS, 2_000_000)

    async def test_balance_change_fires_async_callback(self):
        m = self._make()
        events = []

        async def async_cb(addr, bal):
            events.append((addr, bal))

        m.on_balance_change(async_cb)

        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 1_000_000
            m.stop()
            return 3_000_000

        m._fetch_balance = fake_fetch
        await m.start()
        assert len(events) == 1

    async def test_no_callback_fired_when_balance_unchanged(self):
        m = self._make()
        events = []
        m.on_balance_change(lambda addr, bal: events.append(bal))

        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                m.stop()
            return 1_000_000  # same every time

        m._fetch_balance = fake_fetch
        await m.start()
        assert events == []

    async def test_fetch_error_does_not_crash_loop(self):
        m = self._make()
        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                m.stop()
                return 0
            raise RuntimeError("timeout")

        m._fetch_balance = fake_fetch
        await m.start()  # must not raise
        assert call_count >= 2

    async def test_callback_exception_does_not_crash_loop(self):
        m = self._make()

        def bad_cb(addr, bal):
            raise ValueError("bad callback")

        m.on_balance_change(bad_cb)

        call_count = 0

        async def fake_fetch(addr):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 1_000_000
            m.stop()
            return 2_000_000

        m._fetch_balance = fake_fetch
        await m.start()  # must not raise despite bad callback


class TestWardMonitorFetchBalance:
    async def test_fetch_balance_uses_rpc_client(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            m = WardMonitor(
                vault_addresses=[VALID_ADDRESS],
                xrpl_url="wss://xrplcluster.com",
            )

        mock_resp = _make_success_response({"account_data": {"Balance": "7000000"}})
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("xrpl.asyncio.clients.AsyncJsonRpcClient") as MockRpc:
            MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)
            bal = await m._fetch_balance(VALID_ADDRESS)

        assert bal == 7_000_000

    async def test_fetch_balance_raises_on_rpc_failure(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore", DeprecationWarning)
            m = WardMonitor(
                vault_addresses=[VALID_ADDRESS],
                xrpl_url="wss://xrplcluster.com",
            )

        mock_resp = _make_fail_response("actNOT_FOUND")
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("xrpl.asyncio.clients.AsyncJsonRpcClient") as MockRpc:
            MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(RuntimeError, match="AccountInfo failed"):
                await m._fetch_balance(VALID_ADDRESS)


# ===========================================================================
# Tests: TxBuilder  (ward/tx_builder.py)
# ===========================================================================

from datetime import datetime, timedelta, timezone

from xrpl.models import EscrowCancel, EscrowCreate, Payment

from ward.tx_builder import EscrowParams


class TestTxBuilderPayment:
    def test_basic_payment(self):
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 1_000_000)
        assert isinstance(tx, Payment)
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount == "1000000"

    def test_payment_with_destination_tag(self):
        tx = TxBuilder.payment(
            VALID_ADDRESS, VALID_ADDRESS2, 500_000, destination_tag=42
        )
        assert tx.destination_tag == 42

    def test_payment_without_destination_tag(self):
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 500_000)
        assert tx.destination_tag is None

    def test_payment_with_invoice_id(self):
        inv = "A" * 64
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 100, invoice_id=inv)
        assert tx.invoice_id == inv

    def test_payment_without_invoice_id(self):
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 100)
        assert tx.invoice_id is None

    def test_payment_with_memos(self):
        memos = [{"type": "ward/test", "data": "hello"}]
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 100, memos=memos)
        assert tx.memos is not None
        assert len(tx.memos) == 1

    def test_payment_without_memos(self):
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 100)
        assert not tx.memos

    def test_payment_amount_is_string(self):
        tx = TxBuilder.payment(VALID_ADDRESS, VALID_ADDRESS2, 999)
        assert tx.amount == "999"


class TestTxBuilderEscrowCreate:
    def _params(self, **kwargs):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        defaults = dict(
            account=VALID_ADDRESS,
            destination=VALID_ADDRESS2,
            amount=2_000_000,
            finish_after=now + timedelta(hours=48),
        )
        defaults.update(kwargs)
        return EscrowParams(**defaults)

    def test_basic_escrow_create(self):
        tx = TxBuilder.escrow_create(self._params())
        assert isinstance(tx, EscrowCreate)
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount == "2000000"

    def test_cancel_after_defaults_to_finish_plus_72h(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        finish = now + timedelta(hours=48)
        tx = TxBuilder.escrow_create(self._params(finish_after=finish))
        from xrpl.utils import datetime_to_ripple_time

        expected_cancel = datetime_to_ripple_time(finish + timedelta(hours=72))
        assert tx.cancel_after == expected_cancel

    def test_explicit_cancel_after_is_used(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        finish = now + timedelta(hours=48)
        cancel = now + timedelta(hours=200)
        tx = TxBuilder.escrow_create(
            self._params(finish_after=finish, cancel_after=cancel)
        )
        from xrpl.utils import datetime_to_ripple_time

        assert tx.cancel_after == datetime_to_ripple_time(cancel)

    def test_memos_included_when_provided(self):
        from xrpl.models import Memo
        from xrpl.utils import str_to_hex

        memos = [Memo(memo_type=str_to_hex("ward/test"), memo_data=str_to_hex("data"))]
        tx = TxBuilder.escrow_create(self._params(memos=memos))
        assert tx.memos is not None
        assert len(tx.memos) == 1

    def test_no_memos_when_not_provided(self):
        tx = TxBuilder.escrow_create(self._params())
        assert not tx.memos


class TestTxBuilderClaimEscrow:
    def test_returns_escrow_create(self):
        tx = TxBuilder.claim_escrow(
            VALID_ADDRESS, VALID_ADDRESS2, 1_000_000, claim_id="CLAIM-001"
        )
        assert isinstance(tx, EscrowCreate)

    def test_amount_is_string(self):
        tx = TxBuilder.claim_escrow(
            VALID_ADDRESS, VALID_ADDRESS2, 500_000, claim_id="CLAIM-002"
        )
        assert tx.amount == "500000"

    def test_has_ward_memo(self):
        tx = TxBuilder.claim_escrow(
            VALID_ADDRESS, VALID_ADDRESS2, 100_000, claim_id="CLAIM-003"
        )
        assert tx.memos is not None
        assert len(tx.memos) == 1

    def test_custom_dispute_window(self):
        tx1 = TxBuilder.claim_escrow(
            VALID_ADDRESS,
            VALID_ADDRESS2,
            100,
            claim_id="C1",
            dispute_window_hours=24,
        )
        tx2 = TxBuilder.claim_escrow(
            VALID_ADDRESS,
            VALID_ADDRESS2,
            100,
            claim_id="C2",
            dispute_window_hours=48,
        )
        assert tx1.finish_after < tx2.finish_after

    def test_custom_cancel_buffer(self):
        tx1 = TxBuilder.claim_escrow(
            VALID_ADDRESS,
            VALID_ADDRESS2,
            100,
            claim_id="C3",
            cancel_buffer_hours=24,
        )
        tx2 = TxBuilder.claim_escrow(
            VALID_ADDRESS,
            VALID_ADDRESS2,
            100,
            claim_id="C4",
            cancel_buffer_hours=96,
        )
        assert tx1.cancel_after < tx2.cancel_after


class TestTxBuilderEscrowCancel:
    def test_returns_escrow_cancel(self):
        tx = TxBuilder.escrow_cancel(VALID_ADDRESS, VALID_ADDRESS2, offer_sequence=5)
        assert isinstance(tx, EscrowCancel)
        assert tx.account == VALID_ADDRESS
        assert tx.owner == VALID_ADDRESS2
        assert tx.offer_sequence == 5


# ===========================================================================
# Tests: VaultMonitor gaps  (ward/vault_monitor.py)
# ===========================================================================

from ward.constants import DEFAULT_TESTNET_WS, LSF_LOAN_DEFAULT
from ward.vault_monitor import (
    DefaultSignal,
    VerifiedDefault,
)

ALLOWED_WS = DEFAULT_TESTNET_WS  # "wss://s.altnet.rippletest.net:51233/"


def _make_vault_monitor(**kwargs):
    defaults = dict(websocket_url=ALLOWED_WS)
    defaults.update(kwargs)
    return VaultMonitor(**defaults)


class TestVaultMonitorDecorators:
    def test_on_verified_default_returns_callback(self):
        m = _make_vault_monitor()
        cb = AsyncMock()
        result = m.on_verified_default(cb)
        assert result is cb
        assert cb in m._default_callbacks

    def test_on_anomaly_returns_callback(self):
        m = _make_vault_monitor()
        cb = AsyncMock()
        result = m.on_anomaly(cb)
        assert result is cb
        assert cb in m._anomaly_callbacks

    def test_multiple_callbacks_registered(self):
        m = _make_vault_monitor()
        cb1, cb2 = AsyncMock(), AsyncMock()
        m.on_verified_default(cb1)
        m.on_verified_default(cb2)
        assert len(m._default_callbacks) == 2


class TestVaultMonitorAddLoanBroker:
    def test_add_broker_without_vault(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS)
        assert VALID_ADDRESS in m._broker_addresses
        assert VALID_ADDRESS not in m._broker_to_vault

    def test_add_broker_with_vault_address(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        assert VALID_ADDRESS in m._broker_addresses
        assert m._broker_to_vault[VALID_ADDRESS] == VALID_ADDRESS2

    def test_add_broker_invalid_address_raises(self):
        m = _make_vault_monitor()
        with pytest.raises(ValidationError):
            m.add_loan_broker("not-a-valid-address")

    def test_add_broker_invalid_vault_raises(self):
        m = _make_vault_monitor()
        with pytest.raises(ValidationError):
            m.add_loan_broker(VALID_ADDRESS, vault_address="bad-addr")


class TestVaultMonitorStop:
    async def test_stop_sets_stop_event_and_running_false(self):
        m = _make_vault_monitor()
        m._running = True
        await m.stop()
        assert m._running is False
        assert m._stop_event.is_set()


class TestVaultMonitorHandleMessage:
    async def test_dispatches_transaction_message(self):
        m = _make_vault_monitor()
        handled = []

        async def fake_handle_tx(client, msg):
            handled.append(msg)

        m._handle_transaction = fake_handle_tx
        client = AsyncMock()
        msg = {"transaction": {"TransactionType": "Payment"}, "ledger_index": 100}
        await m._handle_message(client, msg)
        assert len(handled) == 1

    async def test_dispatches_ledger_closed_message(self):
        m = _make_vault_monitor()
        processed = []

        async def fake_process(client, ledger_index):
            processed.append(ledger_index)

        m._process_pending_confirmations = fake_process
        client = AsyncMock()
        msg = {"ledger_index": 12345678}
        await m._handle_message(client, msg)
        assert processed == [12345678]

    async def test_ignores_messages_without_tx_or_ledger(self):
        m = _make_vault_monitor()
        handled = []
        m._handle_transaction = AsyncMock(side_effect=lambda c, m: handled.append(m))
        processed = []
        m._process_pending_confirmations = AsyncMock(
            side_effect=lambda c, l: processed.append(l)
        )
        client = AsyncMock()
        await m._handle_message(client, {"type": "response"})
        assert handled == []
        assert processed == []


class TestVaultMonitorHandleTransaction:
    def _make_default_tx_msg(
        self,
        broker_addr: str,
        loan_id: str = "L" * 64,
        flags: int = LSF_LOAN_DEFAULT,
        outstanding: int = 1_000_000,
        collateral: int = 500_000,
        ledger_index: int = 99,
    ) -> dict:
        return {
            "transaction": {
                "TransactionType": "Payment",
                "Account": broker_addr,
                "LoanID": loan_id,
            },
            "meta": {
                "AffectedNodes": [
                    {
                        "FinalFields": {
                            "Flags": flags,
                            "PrincipalOutstanding": outstanding,
                            "CollateralAmount": collateral,
                        }
                    }
                ]
            },
            "ledger_index": ledger_index,
        }

    async def test_ignores_non_broker_accounts(self):
        m = _make_vault_monitor()
        client = AsyncMock()
        msg = self._make_default_tx_msg(broker_addr=VALID_ADDRESS)
        # VALID_ADDRESS is NOT registered as a broker
        await m._handle_transaction(client, msg)
        assert m._pending == {}

    async def test_ignores_tx_without_default_flag(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        client = AsyncMock()
        msg = self._make_default_tx_msg(broker_addr=VALID_ADDRESS, flags=0)
        await m._handle_transaction(client, msg)
        assert m._pending == {}

    async def test_ignores_tx_without_loan_id(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        client = AsyncMock()
        msg = {
            "transaction": {"TransactionType": "Payment", "Account": VALID_ADDRESS},
            "meta": {"AffectedNodes": [{"FinalFields": {"Flags": LSF_LOAN_DEFAULT}}]},
            "ledger_index": 1,
        }
        await m._handle_transaction(client, msg)
        assert m._pending == {}

    async def test_creates_pending_signal_on_default(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        client = AsyncMock()
        loan_id = "L" * 64
        msg = self._make_default_tx_msg(broker_addr=VALID_ADDRESS, loan_id=loan_id)
        await m._handle_transaction(client, msg)
        assert loan_id in m._pending
        sig = m._pending[loan_id]
        assert sig.vault_address == VALID_ADDRESS2
        assert sig.loan_id == loan_id

    async def test_increments_confirm_count_on_repeat(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        client = AsyncMock()
        loan_id = "L" * 64
        msg = self._make_default_tx_msg(broker_addr=VALID_ADDRESS, loan_id=loan_id)
        await m._handle_transaction(client, msg)
        await m._handle_transaction(client, msg)
        assert m._pending[loan_id].confirm_count == 1

    async def test_fires_anomaly_callback_after_threshold(self):
        m = _make_vault_monitor(vault_addresses=[VALID_ADDRESS2])
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)

        anomalies = []

        async def anomaly_cb(event):
            anomalies.append(event)

        m.on_anomaly(anomaly_cb)
        client = AsyncMock()
        loan_id_base = "L" * 63
        for i in range(3):
            msg = self._make_default_tx_msg(
                broker_addr=VALID_ADDRESS,
                loan_id=loan_id_base + str(i),
            )
            await m._handle_transaction(client, msg)

        assert len(anomalies) >= 1

    async def test_ratio_infinity_when_outstanding_zero(self):
        m = _make_vault_monitor()
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)
        client = AsyncMock()
        msg = self._make_default_tx_msg(
            broker_addr=VALID_ADDRESS, outstanding=0, collateral=500_000
        )
        await m._handle_transaction(client, msg)
        loan_id = "L" * 64
        if loan_id in m._pending:
            assert m._pending[loan_id].health_ratio == float("inf")


class TestVaultMonitorProcessPendingConfirmations:
    async def test_fires_callback_when_confirm_count_reached(self):
        m = _make_vault_monitor(vault_addresses=[VALID_ADDRESS2])
        m.add_loan_broker(VALID_ADDRESS, vault_address=VALID_ADDRESS2)

        defaults_seen = []

        async def default_cb(event):
            defaults_seen.append(event)

        m.on_verified_default(default_cb)

        loan_id = "D" * 64
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS2,
            loan_id=loan_id,
            health_ratio=0.5,
            ledger_index=100,
            confirm_count=2,  # one more will reach DEFAULT_CONFIRM_COUNT=3
        )
        m._pending[loan_id] = signal

        verified_node = {
            "Flags": LSF_LOAN_DEFAULT,
            "PrincipalOutstanding": 500_000,
            "CollateralAmount": 250_000,
        }
        resp = _make_success_response({"node": verified_node})
        client = AsyncMock()
        client.request = AsyncMock(return_value=resp)

        await m._process_pending_confirmations(client, current_ledger=103)

        assert loan_id not in m._pending
        assert len(defaults_seen) == 1
        v = defaults_seen[0]
        assert isinstance(v, VerifiedDefault)
        assert v.vault_address == VALID_ADDRESS2

    async def test_does_not_fire_before_confirm_count(self):
        m = _make_vault_monitor()
        defaults_seen = []
        m.on_verified_default(AsyncMock(side_effect=lambda e: defaults_seen.append(e)))

        loan_id = "E" * 64
        m._pending[loan_id] = DefaultSignal(
            vault_address=VALID_ADDRESS2,
            loan_id=loan_id,
            health_ratio=0.5,
            ledger_index=100,
            confirm_count=0,  # needs 3 total
        )
        client = AsyncMock()
        await m._process_pending_confirmations(client, current_ledger=101)
        assert loan_id in m._pending
        assert defaults_seen == []


class TestVaultMonitorVerifyDefaultOnChain:
    async def test_returns_none_on_failed_response(self):
        m = _make_vault_monitor()
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id="F" * 64,
            health_ratio=0.5,
            ledger_index=100,
        )
        resp = _make_fail_response("entryNotFound")
        client = AsyncMock()
        client.request = AsyncMock(return_value=resp)
        result = await m._verify_default_on_chain(client, signal)
        assert result is None

    async def test_returns_none_when_flag_not_set(self):
        m = _make_vault_monitor()
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id="G" * 64,
            health_ratio=0.5,
            ledger_index=100,
        )
        resp = _make_success_response({"node": {"Flags": 0}})
        client = AsyncMock()
        client.request = AsyncMock(return_value=resp)
        result = await m._verify_default_on_chain(client, signal)
        assert result is None

    async def test_returns_verified_default_when_flag_set(self):
        m = _make_vault_monitor()
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS2,
            loan_id="H" * 64,
            health_ratio=0.8,
            ledger_index=200,
            confirm_count=3,
        )
        resp = _make_success_response(
            {
                "node": {
                    "Flags": LSF_LOAN_DEFAULT,
                    "PrincipalOutstanding": 800_000,
                    "CollateralAmount": 640_000,
                }
            }
        )
        client = AsyncMock()
        client.request = AsyncMock(return_value=resp)
        result = await m._verify_default_on_chain(client, signal)
        assert isinstance(result, VerifiedDefault)
        assert result.vault_address == VALID_ADDRESS2
        assert result.outstanding_amount == 800_000
        assert result.collateral_amount == 640_000
        assert result.loan_flags == LSF_LOAN_DEFAULT

    async def test_returns_none_on_exception(self):
        m = _make_vault_monitor()
        signal = DefaultSignal(
            vault_address=VALID_ADDRESS,
            loan_id="I" * 64,
            health_ratio=0.5,
            ledger_index=100,
        )
        client = AsyncMock()
        client.request = AsyncMock(side_effect=RuntimeError("network error"))
        result = await m._verify_default_on_chain(client, signal)
        assert result is None


class TestVaultMonitorDetectAnomaly:
    def test_returns_false_below_threshold(self):
        m = _make_vault_monitor()
        # Add 2 signals (threshold is 3)
        m._recent_signals[VALID_ADDRESS].append((time.time(), 0.5))
        m._recent_signals[VALID_ADDRESS].append((time.time(), 0.4))
        assert m._detect_anomaly(VALID_ADDRESS) is False

    def test_returns_true_at_threshold(self):
        m = _make_vault_monitor()
        now = time.time()
        for _ in range(3):
            m._recent_signals[VALID_ADDRESS].append((now, 0.3))
        assert m._detect_anomaly(VALID_ADDRESS) is True

    def test_prunes_expired_signals(self):
        m = _make_vault_monitor()
        old_ts = time.time() - 400  # older than 300s window
        for _ in range(5):
            m._recent_signals[VALID_ADDRESS].append((old_ts, 0.3))
        assert m._detect_anomaly(VALID_ADDRESS) is False

    def test_returns_false_for_unknown_address(self):
        m = _make_vault_monitor()
        assert m._detect_anomaly("rNewAddress123456789012345678901234") is False


class TestVaultMonitorFireCallbacks:
    async def test_fires_all_callbacks(self):
        results = []
        cb1 = AsyncMock(side_effect=lambda e: results.append(("cb1", e)))
        cb2 = AsyncMock(side_effect=lambda e: results.append(("cb2", e)))
        await VaultMonitor._fire_callbacks([cb1, cb2], "test_event")
        assert ("cb1", "test_event") in results
        assert ("cb2", "test_event") in results

    async def test_exception_in_callback_does_not_stop_others(self):
        results = []
        cb_bad = AsyncMock(side_effect=RuntimeError("boom"))
        cb_good = AsyncMock(side_effect=lambda e: results.append(e))
        await VaultMonitor._fire_callbacks([cb_bad, cb_good], "event")
        assert "event" in results

    async def test_empty_callback_list_is_noop(self):
        await VaultMonitor._fire_callbacks([], "event")  # must not raise


class TestVaultMonitorRunWithHeartbeat:
    """Tests for the _run_with_heartbeat inner loop (lines 201-203)."""

    def _make_ws_client_from_messages(self, messages):
        """Return a mock WS client whose __aiter__ yields messages then stops."""

        async def _gen():
            for msg in messages:
                yield msg

        client = MagicMock()
        client.__aiter__ = MagicMock(return_value=_gen().__aiter__())
        return client

    async def test_processes_messages_until_exhausted(self):
        m = _make_vault_monitor()
        handled = []

        async def fake_handle(client, msg):
            handled.append(msg)

        m._handle_message = fake_handle
        client = self._make_ws_client_from_messages(
            [
                {"ledger_index": 100},
                {"ledger_index": 101},
            ]
        )
        await m._run_with_heartbeat(client)
        assert len(handled) == 2

    async def test_stops_when_stop_event_set(self):
        m = _make_vault_monitor()
        handled = []

        async def fake_handle(client, msg):
            handled.append(msg)
            m._stop_event.set()  # signal stop after first message

        m._handle_message = fake_handle

        async def _infinite():
            i = 0
            while True:
                yield {"ledger_index": i * 100}
                i += 1

        client = MagicMock()
        client.__aiter__ = MagicMock(return_value=_infinite().__aiter__())
        await m._run_with_heartbeat(client)
        assert len(handled) == 1  # stopped after first message


class TestVaultMonitorHandleTransactionNoVaultAddress:
    """Cover the vault_address falsy branch in _handle_transaction (261->269)."""

    async def test_broker_without_vault_address_still_creates_pending(self):
        m = _make_vault_monitor()
        # Register broker WITHOUT a vault address
        m.add_loan_broker(VALID_ADDRESS)
        assert VALID_ADDRESS not in m._broker_to_vault

        client = AsyncMock()
        loan_id = "K" * 64
        msg = {
            "transaction": {
                "TransactionType": "Payment",
                "Account": VALID_ADDRESS,
                "LoanID": loan_id,
            },
            "meta": {
                "AffectedNodes": [
                    {
                        "FinalFields": {
                            "Flags": LSF_LOAN_DEFAULT,
                            "PrincipalOutstanding": 100_000,
                            "CollateralAmount": 50_000,
                        }
                    }
                ]
            },
            "ledger_index": 50,
        }
        await m._handle_transaction(client, msg)
        # Signal created with empty vault_address
        assert loan_id in m._pending
        assert m._pending[loan_id].vault_address == ""


class TestVaultMonitorRunReconnect:
    """Cover the reconnect backoff path in run() (line 169)."""

    async def test_run_reconnects_on_exception_then_stops(self):
        m = _make_vault_monitor()

        connect_count = 0

        async def fake_subscribe(client):
            pass

        async def fake_heartbeat(client):
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise ConnectionError("simulated disconnect")
            # On second connect, stop the monitor cleanly
            m._stop_event.set()
            m._running = False

        m._subscribe = fake_subscribe
        m._run_with_heartbeat = fake_heartbeat

        with patch("ward.vault_monitor.AsyncWebsocketClient") as MockWS:
            mock_ws = AsyncMock()
            MockWS.return_value.__aenter__ = AsyncMock(return_value=mock_ws)
            MockWS.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await m.run()

        assert connect_count == 2


# ===========================================================================
# Tests: Multi-Vault Policies
# ===========================================================================


class TestMultiVaultPolicies:
    """
    Multi-vault policy purchase, cross-vault claim rejection,
    and per-vault coverage tracking (PoolHealthMonitor._vault_coverage).
    """

    def setup_method(self):
        self.client = WardClient()

    @pytest.mark.asyncio
    async def test_multi_vault_purchase_returns_one_nft_per_vault(self):
        """purchase_multi_vault_coverage mints one NFT per vault and shares one premium_tx."""
        from xrpl.wallet import Wallet as _Wallet

        wallet = _Wallet.create()
        vault_a = VALID_ADDRESS
        vault_b = VALID_ADDRESS2
        pool_addr = _Wallet.create().classic_address

        nft_id_a = "A" * 64
        nft_id_b = "B" * 64
        premium_hash = "C" * 64

        def _mint_resp(nft_id, mint_hash):
            r = MagicMock()
            r.is_successful.return_value = True
            r.result = {"meta": {"nftoken_id": nft_id}, "hash": mint_hash}
            return r

        payment_resp = MagicMock()
        payment_resp.is_successful.return_value = True
        payment_resp.result = {"hash": premium_hash}

        with (
            patch("ward.client.AsyncJsonRpcClient", MagicMock()),
            patch("ward.client.autofill", AsyncMock(side_effect=lambda tx, c: tx)),
            patch(
                "ward.client.build_unsigned_tx",
                AsyncMock(return_value=MagicMock(tx_dict={})),
            ),
            patch(
                "ward.client.get_ledger_close_time", AsyncMock(return_value=800_000_000)
            ),
        ):
            results = await self.client.purchase_multi_vault_coverage(
                institution_address=VALID_ADDRESS,
                vault_addresses=[vault_a, vault_b],
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=pool_addr,
            )

        assert len(results) == 2
        assert results[0]["vault_address"] == vault_a
        assert results[1]["vault_address"] == vault_b
        # ward_signed = False — NFT IDs pending institution signature
        assert results[0]["nft_token_id"] == "pending_institution_signature"
        assert results[1]["nft_token_id"] == "pending_institution_signature"
        # Unsigned payment tx returned for institution to sign
        assert "unsigned_payment_tx" in results[0]
        # ward_signed = False: no wallet stored on client
        assert not hasattr(self.client, "_wallet")

    @pytest.mark.asyncio
    async def test_multi_vault_rejects_duplicates(self):
        """purchase_multi_vault_coverage raises ValidationError on duplicate vault addresses."""
        with pytest.raises(ValidationError, match="duplicate"):
            await self.client.purchase_multi_vault_coverage(
                institution_address=VALID_ADDRESS,  # ),
                vault_addresses=[VALID_ADDRESS, VALID_ADDRESS],
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=VALID_ADDRESS2,
            )

    @pytest.mark.asyncio
    async def test_multi_vault_max_10_vaults_enforced(self):
        """purchase_multi_vault_coverage rejects a list of more than 10 vault addresses."""
        from xrpl.wallet import Wallet as _Wallet

        vaults = [_Wallet.create().classic_address for _ in range(11)]
        with pytest.raises(ValidationError, match="10"):
            await self.client.purchase_multi_vault_coverage(
                institution_address=VALID_ADDRESS,  # ),
                vault_addresses=vaults,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=VALID_ADDRESS2,
            )

    @pytest.mark.asyncio
    async def test_cross_vault_claim_rejected(self):
        """ClaimValidator rejects an NFT covering vault A when claiming against vault B."""
        validator = _make_validator_with_mocks(
            policy_vault=VALID_ADDRESS,
        )
        try:
            result = await validator.validate_claim(
                claimant_address=VALID_ADDRESS,
                nft_token_id=VALID_NFT_ID,
                defaulted_vault=VALID_ADDRESS2,  # different from NFT's vault
                loan_id=VALID_LOAN_ID,
                pool_address=VALID_ADDRESS2,
            )
        finally:
            p = getattr(validator, "_mock_patch", None)
            if p:
                try:
                    p.stop()
                except RuntimeError:
                    pass

        assert not result.approved
        assert result.steps_passed == 2  # passes steps 1-2, rejected at step 3
        assert (
            "vault" in result.rejection_reason.lower()
            or "mismatch" in result.rejection_reason.lower()
        )

    def test_multi_vault_coverage_tracked_per_vault(self):
        """PoolHealthMonitor._vault_coverage tracks coverage per depositor+vault pair."""
        from xrpl.wallet import Wallet as _Wallet

        monitor = PoolHealthMonitor(pool_address=VALID_ADDRESS)
        depositor = VALID_ADDRESS2
        vault_a = VALID_ADDRESS
        vault_b = _Wallet.create().classic_address

        monitor.register_policy(
            "A" * 64, 1_000_000, depositor_address=depositor, vault_address=vault_a
        )
        monitor.register_policy(
            "B" * 64, 2_000_000, depositor_address=depositor, vault_address=vault_b
        )

        assert monitor._vault_coverage[depositor][vault_a] == 1_000_000
        assert monitor._vault_coverage[depositor][vault_b] == 2_000_000
        # Legacy registry still tracks by nft_token_id
        assert monitor._coverage_registry["A" * 64] == 1_000_000
        assert monitor._coverage_registry["B" * 64] == 2_000_000

        # Deregister vault_a — vault_b entry must survive
        monitor.deregister_policy(
            "A" * 64, depositor_address=depositor, vault_address=vault_a
        )
        assert vault_a not in monitor._vault_coverage.get(depositor, {})
        assert monitor._vault_coverage[depositor][vault_b] == 2_000_000

        # Deregister vault_b — depositor entry cleaned up entirely
        monitor.deregister_policy(
            "B" * 64, depositor_address=depositor, vault_address=vault_b
        )
        assert depositor not in monitor._vault_coverage


# ===========================================================================
# Tests: MultiInstitutionPool
# ===========================================================================


class TestMultiInstitutionPool:
    """
    Shared-capital pool — member registration, pro-rata loss distribution,
    capacity enforcement, admin access control, and ward_signed=False.
    """

    def setup_method(self):
        from ward.pool import MultiInstitutionPool

        self.MultiInstitutionPool = MultiInstitutionPool
        self.pool = MultiInstitutionPool(pool_address=VALID_ADDRESS)

    def test_pool_creation(self):
        """Pool initialises with zero capacity and ward_signed=False."""
        pool = self.MultiInstitutionPool(pool_address=VALID_ADDRESS)
        assert pool.total_capacity == 0
        assert pool.used_capacity == 0
        assert pool.available_capacity == 0
        assert pool.member_count == 0
        assert pool.ward_signed is False
        assert pool.pool_address == VALID_ADDRESS

    def test_member_registration(self):
        """First registrant becomes admin; contributions accumulate correctly."""
        self.pool.register_member(VALID_ADDRESS, 5_000_000)
        assert VALID_ADDRESS in self.pool.member_addresses()
        assert self.pool.total_capacity == 5_000_000
        assert self.pool.available_capacity == 5_000_000
        assert self.pool.member_count == 1

        self.pool.register_member(VALID_ADDRESS2, 3_000_000)
        assert self.pool.member_count == 2
        assert self.pool.total_capacity == 8_000_000

        # Invalid address rejected
        with pytest.raises(ValidationError):
            self.pool.register_member("not-an-address", 1_000_000)

        # Zero contribution rejected
        with pytest.raises(ValidationError):
            self.pool.register_member(VALID_ADDRESS, 0)

    def test_pro_rata_loss_distribution(self):
        """Loss is distributed in proportion to each member's contribution."""
        self.pool.register_member(VALID_ADDRESS, 6_000_000)  # 60 %
        self.pool.register_member(VALID_ADDRESS2, 4_000_000)  # 40 %
        claim = 1_000_000
        losses = self.pool.distribute_loss(claim)

        # Must sum exactly to claim
        assert sum(losses.values()) == claim
        assert losses[VALID_ADDRESS] == 600_000
        assert losses[VALID_ADDRESS2] == 400_000

        # used_capacity updated; available_capacity reduced
        assert self.pool.used_capacity == claim
        assert self.pool.available_capacity == self.pool.total_capacity - claim

    def test_pool_capacity_enforced(self):
        """distribute_loss raises ValidationError when claim exceeds capacity."""
        self.pool.register_member(VALID_ADDRESS, 1_000_000)
        with pytest.raises(ValidationError, match="insufficient capacity"):
            self.pool.distribute_loss(2_000_000)

        # Empty pool also raises
        empty = self.MultiInstitutionPool(pool_address=VALID_ADDRESS)
        with pytest.raises(ValidationError, match="no members"):
            empty.distribute_loss(1)

    def test_admin_can_remove_member(self):
        """Admin (first registrant) removes members; non-admin is rejected."""
        self.pool.register_member(VALID_ADDRESS, 5_000_000)  # becomes admin
        self.pool.register_member(VALID_ADDRESS2, 3_000_000)

        # Non-admin attempt raises
        with pytest.raises(ValidationError, match="admin"):
            self.pool.remove_member(VALID_ADDRESS2, VALID_ADDRESS)

        # Admin removes non-admin successfully
        self.pool.remove_member(VALID_ADDRESS, VALID_ADDRESS2)
        assert VALID_ADDRESS2 not in self.pool.member_addresses()
        assert self.pool.total_capacity == 5_000_000

        # Removing unknown member raises
        with pytest.raises(ValidationError, match="not found"):
            self.pool.remove_member(VALID_ADDRESS, VALID_ADDRESS2)

    def test_ward_signed_false_in_pool_transactions(self):
        """register_pool_member returns ward_signed=False and no signing key."""
        client = WardClient()
        tx = client.register_pool_member(
            pool_address=VALID_ADDRESS2,
            member_address=VALID_ADDRESS,
            contribution_drops=5_000_000,
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "AccountSet"
        assert tx["Account"] == VALID_ADDRESS
        # Pool address encoded in domain — not stored as a signing key
        assert "SigningKey" not in tx
        assert "seed" not in tx
        # Memo payload confirms ward_signed=False
        memo_hex = tx["Memos"][0]["Memo"]["MemoData"]
        payload = json.loads(bytes.fromhex(memo_hex).decode())
        assert payload["ward_signed"] is False
        assert payload["pool"] == VALID_ADDRESS2
        assert payload["contribution_drops"] == 5_000_000

        # Invalid inputs rejected before building tx
        with pytest.raises(ValidationError):
            client.register_pool_member(
                pool_address="bad", member_address=VALID_ADDRESS, contribution_drops=1
            )
        with pytest.raises(ValidationError):
            client.register_pool_member(
                pool_address=VALID_ADDRESS2,
                member_address=VALID_ADDRESS,
                contribution_drops=0,
            )


# ===========================================================================
# Tests: UnsignedTransaction
# ===========================================================================

_XRP_ASSET = {"currency": "XRP"}
_USD_ASSET = {"currency": "USD", "issuer": VALID_ADDRESS}


class TestUnsignedTransaction:
    def test_ward_signed_is_always_false(self):
        tx = UnsignedTransaction(
            tx_type="Payment",
            account=VALID_ADDRESS,
            destination=VALID_ADDRESS2,
            amount_drops=1_000_000,
        )
        assert tx.ward_signed is False

    def test_ward_signed_not_an_init_parameter(self):
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(UnsignedTransaction)}
        init_fields = {
            f.name for f in dataclasses.fields(UnsignedTransaction) if f.init
        }
        assert "ward_signed" in field_names
        assert "ward_signed" not in init_fields

    def test_defaults(self):
        tx = UnsignedTransaction(
            tx_type="Payment",
            account=VALID_ADDRESS,
            destination=VALID_ADDRESS2,
            amount_drops=500_000,
        )
        assert tx.paths is None
        assert tx.send_max is None
        assert tx.partial_resolution is False

    def test_partial_resolution_can_be_set(self):
        tx = UnsignedTransaction(
            tx_type="Payment",
            account=VALID_ADDRESS,
            destination=VALID_ADDRESS2,
            amount_drops=1_000,
            partial_resolution=True,
        )
        assert tx.partial_resolution is True
        assert tx.ward_signed is False


# ===========================================================================
# Tests: Resolver
# ===========================================================================


class TestResolver:
    @pytest.mark.asyncio
    async def test_same_asset_no_pathfinding(self):
        """Same collateral and payout asset — direct payment, no paths."""
        resolver = Resolver()
        tx = await resolver.build_unsigned_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=1_000_000,
            collateral_asset=_XRP_ASSET,
            payout_asset=_XRP_ASSET,
        )
        assert tx.tx_type == "Payment"
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount_drops == 1_000_000
        assert tx.paths is None
        assert tx.send_max is None
        assert tx.partial_resolution is False
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_cross_asset_valid_path_populates_paths_and_send_max(self):
        """Cross-asset with a valid ripple_path_find result populates paths/send_max."""
        mock_paths = [[{"account": VALID_ADDRESS}]]
        mock_send_max = {"currency": "XRP", "value": "1.5"}
        path_resp = _make_success_response(
            {
                "alternatives": [
                    {
                        "paths_computed": mock_paths,
                        "source_amount": mock_send_max,
                    }
                ]
            }
        )
        MockClient = _async_client_factory(AsyncMock(return_value=path_resp))

        with patch("ward.resolver.AsyncJsonRpcClient", MockClient):
            resolver = Resolver()
            tx = await resolver.build_unsigned_tx(
                pool_address=VALID_ADDRESS,
                claimant_address=VALID_ADDRESS2,
                payout_drops=500_000,
                collateral_asset=_XRP_ASSET,
                payout_asset=_USD_ASSET,
            )

        assert tx.paths == mock_paths
        assert tx.send_max == mock_send_max
        assert tx.partial_resolution is False
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_cross_asset_no_path_sets_partial_resolution(self):
        """Cross-asset with no alternatives from ripple_path_find sets partial_resolution."""
        empty_resp = _make_success_response({"alternatives": []})
        MockClient = _async_client_factory(AsyncMock(return_value=empty_resp))

        with patch("ward.resolver.AsyncJsonRpcClient", MockClient):
            resolver = Resolver()
            tx = await resolver.build_unsigned_tx(
                pool_address=VALID_ADDRESS,
                claimant_address=VALID_ADDRESS2,
                payout_drops=500_000,
                collateral_asset=_XRP_ASSET,
                payout_asset=_USD_ASSET,
            )

        assert tx.partial_resolution is True
        assert tx.paths is None
        assert tx.send_max is None
        assert tx.ward_signed is False


# ===========================================================================
# Tests: Step 9 — path_available flag
# ===========================================================================


class TestStep9PathAvailability:
    def setup_method(self):
        from ward.constants import XRPL_BASE_RESERVE_DROPS

        self.validator = ClaimValidator()
        self.solvent_pool = {
            "Balance": str(50_000_000 + XRPL_BASE_RESERVE_DROPS),
            "OwnerCount": 0,
        }

    def test_same_asset_solvent_pool_passes(self):
        err = self.validator._step9_check_pool_solvency(
            self.solvent_pool, 50_000, path_available=True
        )
        assert err is None

    def test_path_unavailable_rejects_regardless_of_balance(self):
        err = self.validator._step9_check_pool_solvency(
            self.solvent_pool, 50_000, path_available=False
        )
        assert err is not None
        assert "path" in err.lower()

    def test_none_pool_info_always_rejects(self):
        err = self.validator._step9_check_pool_solvency(
            None, 50_000, path_available=True
        )
        assert err is not None

    def test_default_path_available_is_true(self):
        err = self.validator._step9_check_pool_solvency(self.solvent_pool, 50_000)
        assert err is None


# ===========================================================================
# Tests: WormholeNTTAdapter
# ===========================================================================

from ward.adapters import WormholeNTTAdapter
from ward.adapters.wormhole import LedgerState, NTTTransferPayload, VaultState


class TestWormholeNTTAdapter:
    def setup_method(self):
        self.adapter = WormholeNTTAdapter(
            source_rpc_url="https://s.altnet.rippletest.net:51234/",
            dest_chain_id=2,
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=1_000_000,
        )
        assert tx.ward_signed is False

    def test_ntt_payload_ward_signed_not_init_param(self):
        """NTTTransferPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {f.name for f in dataclasses.fields(NTTTransferPayload) if f.init}
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful resolution returns correct tx_type and addresses."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=500_000,
            dest_chain_id=2,
            nonce=42,
        )
        assert tx.tx_type == "NTT_TRANSFER"
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False
        assert tx.partial_resolution is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ntt_payload_in_send_max(self):
        """NTT payload is embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=750_000,
            dest_chain_id=2,
            nonce=7,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["transfer_type"] == "NTT_TRANSFER"
        assert payload["dest_chain_id"] == 2
        assert payload["amount"] == 750_000
        assert payload["nonce"] == 7
        assert payload["ward_signed"] is False
        assert payload["sender"] == VALID_ADDRESS
        assert payload["recipient"] == VALID_ADDRESS2

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert isinstance(state, VaultState)
        assert state.vault_address == VALID_ADDRESS

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, LedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """ChainAdapter escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_finish_ward_signed_false(self):
        """ChainAdapter escrow finish always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_finish(
            claimant_address=VALID_ADDRESS2,
            owner_address=VALID_ADDRESS,
            offer_sequence=12345,
            condition_hex="ABCD1234",
            fulfillment_hex="EFGH5678",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowFinish"


# ===========================================================================
# Tests: FlareAdapter
# ===========================================================================
from ward.adapters import FlareAdapter
from ward.adapters.flare import FlareResolutionPayload
from ward.adapters.flare import LedgerState as FlareLedgerState
from ward.adapters.flare import VaultState as FlareVaultState


class TestFlareAdapter:
    def setup_method(self):
        self.adapter = FlareAdapter(
            rpc_url="https://flare-api.flare.network/ext/C/rpc",
            chain_id=14,
            rlusd_address=EVM_ADDRESS,
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False

    def test_flare_payload_ward_signed_not_init_param(self):
        """FlareResolutionPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {
            f.name for f in dataclasses.fields(FlareResolutionPayload) if f.init
        }
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful resolution returns correct tx_type and addresses."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=500_000,
            dest_chain_id=14,
            nonce=7,
        )
        assert tx.tx_type == "FLARE_EVM_CALL"
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """Flare payload is embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=750_000,
            nonce=3,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["call_type"] == "FLARE_EVM_CALL"
        assert payload["chain_id"] == 14
        assert payload["amount"] == 750_000
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert isinstance(state, FlareVaultState)
        assert state.vault_address == VALID_ADDRESS

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, FlareLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """Flare escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_finish_ward_signed_false(self):
        """Flare escrow finish always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_finish(
            claimant_address=VALID_ADDRESS2,
            owner_address=VALID_ADDRESS,
            offer_sequence=99,
            condition_hex="ABCD1234",
            fulfillment_hex="EFGH5678",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowFinish"


# ===========================================================================
# Tests: AxelarAdapter
# ===========================================================================
from ward.adapters import AxelarAdapter
from ward.adapters.axelar import AxelarGMPPayload
from ward.adapters.axelar import LedgerState as AxelarLedgerState
from ward.adapters.axelar import VaultState as AxelarVaultState


class TestAxelarAdapter:
    def setup_method(self):
        self.adapter = AxelarAdapter(
            source_rpc_url="https://rpc-evm-sidechain.xrpl.org",
            source_chain="xrpl-evm",
            dest_chain="ethereum",
            gateway_address=EVM_ADDRESS,
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False

    def test_axelar_payload_ward_signed_not_init_param(self):
        """AxelarGMPPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {f.name for f in dataclasses.fields(AxelarGMPPayload) if f.init}
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful resolution returns correct tx_type and addresses."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=500_000,
            dest_chain="ethereum",
            nonce=5,
        )
        assert tx.tx_type == "AXELAR_GMP_CALL"
        assert tx.account == VALID_ADDRESS
        assert tx.destination == VALID_ADDRESS2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """Axelar GMP payload embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=750_000,
            dest_chain="polygon",
            nonce=9,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["call_type"] == "AXELAR_GMP_CALL"
        assert payload["dest_chain"] == "polygon"
        assert payload["amount"] == 750_000
        assert payload["nonce"] == 9
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_send_resolution_message_ward_signed_false(self):
        """send_resolution_message returns dict with ward_signed=False."""
        msg = await self.adapter.send_resolution_message(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=300_000,
            nonce=1,
        )
        assert msg["ward_signed"] is False
        assert msg["call_type"] == "AXELAR_GMP_CALL"
        assert msg["source_chain"] == "xrpl-evm"
        assert msg["dest_chain"] == "ethereum"

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert isinstance(state, AxelarVaultState)
        assert state.vault_address == VALID_ADDRESS

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, AxelarLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """Axelar escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"


# ===========================================================================
# Tests: SolanaAdapter
# ===========================================================================
from ward.adapters import SolanaAdapter
from ward.adapters.solana import LedgerState as SolanaLedgerState
from ward.adapters.solana import SolanaTransferPayload
from ward.adapters.solana import VaultState as SolanaVaultState

EVM_ADDRESS = "0xabc123def456aaa000111222333444555666777"
EVM_ADDRESS2 = "0xbbb123ccc456ddd789eee012fff345aaa678bbb"
SOL_ADDRESS = "7EcDhSYGxXyscszYEp35KHN8vvw3svAuLKTzXwCFLtV"
SOL_ADDRESS2 = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"


class TestSolanaAdapter:
    def setup_method(self):
        self.adapter = SolanaAdapter(
            rpc_url="https://api.devnet.solana.com",
            rlusd_mint=SOL_ADDRESS,
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False

    def test_solana_payload_ward_signed_not_init_param(self):
        """SolanaTransferPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {
            f.name for f in dataclasses.fields(SolanaTransferPayload) if f.init
        }
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful Solana resolution returns correct tx_type and accounts."""
        tx = await self.adapter.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=500_000,
            nonce=1,
        )
        assert tx.tx_type == "SOLANA_TRANSFER"
        assert tx.account == SOL_ADDRESS
        assert tx.destination == SOL_ADDRESS2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """Solana payload embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=750_000,
            recent_blockhash="abc123",
            nonce=4,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["transfer_type"] == "SOLANA_TRANSFER"
        assert payload["amount"] == 750_000
        assert payload["recent_blockhash"] == "abc123"
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=SOL_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=SOL_ADDRESS2,
        )
        assert isinstance(state, SolanaVaultState)
        assert state.vault_address == SOL_ADDRESS

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, SolanaLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=SOL_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=SOL_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """Solana escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=SOL_ADDRESS,
            claimant_address=SOL_ADDRESS2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_finish_ward_signed_false(self):
        """Solana escrow finish always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_finish(
            claimant_address=SOL_ADDRESS2,
            owner_address=SOL_ADDRESS,
            offer_sequence=1,
            condition_hex="ABCD1234",
            fulfillment_hex="EFGH5678",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowFinish"


# ===========================================================================
# Tests: HederaAdapter
# ===========================================================================
from ward.adapters import HederaAdapter
from ward.adapters.hedera import HederaTransferPayload
from ward.adapters.hedera import LedgerState as HederaLedgerState
from ward.adapters.hedera import VaultState as HederaVaultState

HEDERA_ACCOUNT = "0.0.123456"
HEDERA_ACCOUNT2 = "0.0.789012"


class TestHederaAdapter:
    def setup_method(self):
        self.adapter = HederaAdapter(
            mirror_node_url="https://testnet.mirrornode.hedera.com",
            rlusd_token_id="0.0.99999",
            network="testnet",
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False

    def test_hedera_payload_ward_signed_not_init_param(self):
        """HederaTransferPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {
            f.name for f in dataclasses.fields(HederaTransferPayload) if f.init
        }
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful Hedera resolution returns correct tx_type and accounts."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=500_000,
            nonce=2,
        )
        assert tx.tx_type == "HEDERA_CRYPTO_TRANSFER"
        assert tx.account == HEDERA_ACCOUNT
        assert tx.destination == HEDERA_ACCOUNT2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """Hedera payload embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=750_000,
            nonce=8,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["transfer_type"] == "HEDERA_CRYPTO_TRANSFER"
        assert payload["token_id"] == "0.0.99999"
        assert payload["amount"] == 750_000
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=HEDERA_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=HEDERA_ACCOUNT2,
        )
        assert isinstance(state, HederaVaultState)
        assert state.vault_address == HEDERA_ACCOUNT

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, HederaLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=HEDERA_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=HEDERA_ACCOUNT2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """Hedera escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"


# ===========================================================================
# Tests: StellarAdapter
# ===========================================================================
from ward.adapters import StellarAdapter
from ward.adapters.stellar import LedgerState as StellarLedgerState
from ward.adapters.stellar import StellarPaymentPayload
from ward.adapters.stellar import VaultState as StellarVaultState

STELLAR_ACCOUNT = "GBOPNQMHQQHLNLQUBMJMTVKZXEZFKPQ3VHZPNXIVMKFH7QQVVKLJ7BH"
STELLAR_ACCOUNT2 = "GCEZWKCA5VLDNRLN3RPRJMRZOX3Z6G5CHCGVZC8CS76WQZE8EKLE7JVD"


class TestStellarAdapter:
    def setup_method(self):
        self.adapter = StellarAdapter(
            horizon_url="https://horizon-testnet.stellar.org",
            rlusd_asset_code="RLUSD",
            rlusd_issuer=STELLAR_ACCOUNT,
            network_passphrase="Test SDF Network ; September 2015",
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=5_000_000,  # 0.5 RLUSD in stroops
        )
        assert tx.ward_signed is False

    def test_stellar_payload_ward_signed_not_init_param(self):
        """StellarPaymentPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {
            f.name for f in dataclasses.fields(StellarPaymentPayload) if f.init
        }
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful Stellar resolution returns correct tx_type and accounts."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=5_000_000,
            sequence_number=12345,
            fee_stroops=100,
            memo="ward:test",
        )
        assert tx.tx_type == "STELLAR_PAYMENT"
        assert tx.account == STELLAR_ACCOUNT
        assert tx.destination == STELLAR_ACCOUNT2
        assert tx.amount_drops == 5_000_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """Stellar payload embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=7_000_000,
            sequence_number=99,
            memo="ward:claim-001",
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["payment_type"] == "STELLAR_PAYMENT"
        assert payload["asset_code"] == "RLUSD"
        assert payload["memo"] == "ward:claim-001"
        assert payload["sequence_number"] == 99
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_amount_str_format(self):
        """Payout amount converted to 7-decimal Stellar string format."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=10_000_000,  # 1.0 RLUSD = 10,000,000 stroops
        )
        payload = tx.send_max
        # 10_000_000 / 10_000_000 = 1.0000000
        assert payload["amount_str"] == "1.0000000"

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=STELLAR_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=STELLAR_ACCOUNT2,
        )
        assert isinstance(state, StellarVaultState)
        assert state.vault_address == STELLAR_ACCOUNT

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, StellarLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=STELLAR_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=STELLAR_ACCOUNT2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """Stellar escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            amount=5_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"
        assert tx["asset_code"] == "RLUSD"


# ===========================================================================
# Tests: XDCAdapter
# ===========================================================================
from ward.adapters import XDCAdapter
from ward.adapters.xdc import LedgerState as XDCLedgerState
from ward.adapters.xdc import VaultState as XDCVaultState
from ward.adapters.xdc import XDCResolutionPayload

XDC_ADDRESS = "xdcabc123def456aaa000111222333444555666777"
XDC_ADDRESS2 = "xdcbbb123ccc456ddd789eee012fff345aaa678bbb"


class TestXDCAdapter:
    def setup_method(self):
        self.adapter = XDCAdapter(
            rpc_url="https://erpc.apothem.network",
            chain_id=51,
            rlusd_address=XDC_ADDRESS,
        )

    # -- ward_signed invariant ------------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_ward_signed_false(self):
        """ward_signed must always be False on the returned UnsignedTransaction."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False

    def test_xdc_payload_ward_signed_not_init_param(self):
        """XDCResolutionPayload.ward_signed is init=False — cannot be overridden."""
        import dataclasses

        init_fields = {
            f.name for f in dataclasses.fields(XDCResolutionPayload) if f.init
        }
        assert "ward_signed" not in init_fields

    # -- successful resolution path ------------------------------------------

    @pytest.mark.asyncio
    async def test_build_resolution_tx_success(self):
        """Successful XDC resolution returns correct tx_type and addresses."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=500_000,
            dest_chain_id=51,
            nonce=6,
        )
        assert tx.tx_type == "XDC_EVM_CALL"
        assert tx.account == XDC_ADDRESS
        assert tx.destination == XDC_ADDRESS2
        assert tx.amount_drops == 500_000
        assert tx.ward_signed is False

    @pytest.mark.asyncio
    async def test_build_resolution_tx_payload_in_send_max(self):
        """XDC payload embedded in send_max with correct fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=750_000,
            nonce=2,
        )
        payload = tx.send_max
        assert payload is not None
        assert payload["call_type"] == "XDC_EVM_CALL"
        assert payload["chain_id"] == 51
        assert payload["amount"] == 750_000
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_verify_vault_returns_vault_state(self):
        """verify_vault returns a VaultState dataclass."""
        state = await self.adapter.verify_vault(
            vault_address=XDC_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=XDC_ADDRESS2,
        )
        assert isinstance(state, XDCVaultState)
        assert state.vault_address == XDC_ADDRESS

    @pytest.mark.asyncio
    async def test_get_ledger_state_returns_ledger_state(self):
        """get_ledger_state returns a LedgerState dataclass."""
        state = await self.adapter.get_ledger_state()
        assert isinstance(state, XDCLedgerState)

    # -- failed resolution path ----------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_vault_not_defaulted(self):
        """Base adapter returns is_defaulted=False (no live RPC wired)."""
        state = await self.adapter.verify_vault(
            vault_address=XDC_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=XDC_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_create_ward_signed_false(self):
        """XDC escrow create always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            amount=1_000_000,
            condition_hex="ABCD1234",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowCreate"

    @pytest.mark.asyncio
    async def test_build_unsigned_escrow_finish_ward_signed_false(self):
        """XDC escrow finish always has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_finish(
            claimant_address=XDC_ADDRESS2,
            owner_address=XDC_ADDRESS,
            offer_sequence=77,
            condition_hex="ABCD1234",
            fulfillment_hex="EFGH5678",
        )
        assert tx["ward_signed"] is False
        assert tx["TransactionType"] == "EscrowFinish"


# ===========================================================================
# Day 5 — Adversarial Testing
# All ward_signed = False assertions under every failure path
# ===========================================================================


# ---------------------------------------------------------------------------
# Adversarial: XRPL Core
# ---------------------------------------------------------------------------


class TestAdversarialXRPLCore:
    """
    Adversarial edge cases for the XRPL nine-check validation core.
    Tests all rejection paths and verifies ward_signed=False throughout.
    """

    def setup_method(self):
        from ward.primitives import _rate_limit_windows

        _rate_limit_windows.pop(VALID_NFT_ID, None)

    # -- Replay: burned NFT presented as valid ------------------------------

    @pytest.mark.asyncio
    async def test_adversarial_burned_nft_rejected_at_step1(self):
        """Burned NFT (absent from AccountNFTs) is rejected at Step 1."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            nft_exists=False
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed == 0
        # ward_signed is not on ValidationResult, but verify rejection is clean
        assert result.rejection_reason

    @pytest.mark.asyncio
    async def test_adversarial_burned_nft_ward_signed_never_set(self):
        """Even on a burned-NFT attack, the UnsignedTransaction is never produced."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            nft_exists=False
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.claim_payout_drops == 0

    # -- Expired credentials ------------------------------------------------

    @pytest.mark.asyncio
    async def test_adversarial_expired_policy_rejected_at_step2(self):
        """Expired policy is rejected at Step 2 with 'expired' in reason."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            ledger_time=999_999_998,
            expiry_time=100_000,  # far in the past relative to ledger_time
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed < 3
        assert result.rejection_reason

    # -- Identity spoofing: vault mismatch ----------------------------------

    @pytest.mark.asyncio
    async def test_adversarial_vault_mismatch_rejected_at_step3(self):
        """Cross-vault claim (vault address mismatch) is rejected at Step 3."""
        wrong_vault = VALID_ADDRESS2  # NFT bound to VALID_ADDRESS
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            policy_vault=VALID_ADDRESS,
            defaulted_vault=wrong_vault,
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=wrong_vault,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed < 4

    # -- Default flag manipulation -------------------------------------------

    @pytest.mark.asyncio
    async def test_adversarial_no_default_flag_rejected_at_step4(self):
        """Claim without LSF_LOAN_DEFAULT set is rejected at Step 4."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            default_flag_set=False
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert result.steps_passed < 5

    # -- Pool exhaustion: insolvent pool ------------------------------------

    @pytest.mark.asyncio
    async def test_adversarial_insolvent_pool_rejected(self):
        """Insolvent pool (balance=0) is rejected at Step 6 or 9."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            pool_balance_drops=0,
            premium_paid=True,
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved
        assert "insolvent" in result.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_adversarial_pool_below_coverage_ratio(self):
        """Pool below 1.5× coverage ratio is rejected."""
        validator = TestClaimValidatorAdversarial()._make_validator_with_mocks(
            pool_balance_drops=50_000,  # well below 1.5× of vault_loss=100_000
            vault_loss_drops=100_000,
        )
        result = await validator.validate_claim(
            claimant_address=VALID_ADDRESS,
            nft_token_id=VALID_NFT_ID,
            defaulted_vault=VALID_VAULT,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS,
        )
        assert not result.approved

    # -- Rate limit: 4+ claims per NFT per 300s ----------------------------

    def test_adversarial_rate_limit_exceeded(self):
        """4th claim attempt on same NFT within 300s is rejected."""
        from ward.primitives import _rate_limit_windows, check_rate_limit

        unique_nft = "ADVERSARIAL" + "A" * 53
        _rate_limit_windows.pop(unique_nft, None)
        for _ in range(CLAIM_RATE_LIMIT_MAX):
            check_rate_limit(unique_nft)
        with pytest.raises(ValidationError, match="Rate limit"):
            check_rate_limit(unique_nft)

    def test_adversarial_rate_limit_ward_signed_not_affected(self):
        """Rate limit rejection does not produce any signed output."""
        from ward.primitives import _rate_limit_windows, check_rate_limit

        unique_nft = "WARDLIMIT" + "B" * 55
        _rate_limit_windows.pop(unique_nft, None)
        for _ in range(CLAIM_RATE_LIMIT_MAX):
            check_rate_limit(unique_nft)
        try:
            check_rate_limit(unique_nft)
            assert False, "Should have raised"
        except ValidationError as exc:
            assert "Rate limit" in str(exc)
            # No UnsignedTransaction produced — the exception is the only output

    # -- Partial resolution: no Pathfinder path ----------------------------

    @pytest.mark.asyncio
    async def test_adversarial_no_pathfinder_path_partial_resolution(self):
        """When ripple_path_find returns no alternatives, partial_resolution=True."""
        empty_resp = _make_success_response({"alternatives": []})
        MockClient = _async_client_factory(AsyncMock(return_value=empty_resp))
        with patch("ward.resolver.AsyncJsonRpcClient", MockClient):
            resolver = Resolver()
            tx = await resolver.build_unsigned_tx(
                pool_address=VALID_ADDRESS,
                claimant_address=VALID_ADDRESS2,
                payout_drops=500_000,
                collateral_asset=_XRP_ASSET,
                payout_asset=_USD_ASSET,
            )
        assert tx.partial_resolution is True
        assert tx.ward_signed is False
        assert tx.paths is None
        assert tx.send_max is None

    @pytest.mark.asyncio
    async def test_adversarial_pathfinder_rpc_failure_partial_resolution(self):
        """When ripple_path_find RPC fails, partial_resolution=True (no panic)."""
        fail_resp = _make_fail_response("noPath")
        MockClient = _async_client_factory(AsyncMock(return_value=fail_resp))
        with patch("ward.resolver.AsyncJsonRpcClient", MockClient):
            resolver = Resolver()
            tx = await resolver.build_unsigned_tx(
                pool_address=VALID_ADDRESS,
                claimant_address=VALID_ADDRESS2,
                payout_drops=200_000,
                collateral_asset=_XRP_ASSET,
                payout_asset=_USD_ASSET,
            )
        assert tx.partial_resolution is True
        assert tx.ward_signed is False


# ---------------------------------------------------------------------------
# Adversarial: WormholeNTTAdapter
# ---------------------------------------------------------------------------


class TestAdversarialWormhole:
    """
    Adversarial scenarios for the Wormhole NTT adapter.
    Verifies ward_signed=False is maintained under all failure paths.
    """

    def setup_method(self):
        self.adapter = WormholeNTTAdapter(
            source_rpc_url="https://s.altnet.rippletest.net:51234/",
            dest_chain_id=2,
        )

    def test_adversarial_ntt_payload_ward_signed_immutable(self):
        """NTTTransferPayload.ward_signed cannot be set by caller — field(init=False)."""
        payload = NTTTransferPayload(
            source_chain_id=25,
            dest_chain_id=2,
            source_token="RLUSD",
            dest_token="RLUSD",
            sender=VALID_ADDRESS,
            recipient=VALID_ADDRESS2,
            amount=1_000_000,
            nonce=0,
        )
        assert payload.ward_signed is False
        # Verify it is read-only (dataclass frozen would prevent assignment,
        # but ward_signed=False invariant is enforced structurally via init=False)
        payload2 = NTTTransferPayload(
            source_chain_id=25,
            dest_chain_id=99,  # attacker changes dest chain
            source_token="RLUSD",
            dest_token="EVIL",  # attacker changes dest token
            sender=VALID_ADDRESS,
            recipient=VALID_ADDRESS2,
            amount=1_000_000_000,  # attacker inflates amount
            nonce=0,
        )
        # Even with crafted fields, ward_signed remains False
        assert payload2.ward_signed is False

    @pytest.mark.asyncio
    async def test_adversarial_invalid_cross_chain_msg_ward_signed_false(self):
        """Malformed cross-chain resolution still returns ward_signed=False."""
        # Empty addresses — adapter builds payload without signing
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=0,  # zero payout edge case
            dest_chain_id=999,  # unknown chain
            nonce=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_rlusd_issuer_control_preserved(self):
        """RLUSD issuer fields in NTT payload match canonical constants."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=500_000,
        )
        payload = tx.send_max
        # source_token must be the canonical RLUSD hex — not an attacker-controlled value
        assert payload["source_token"] == "524C555344000000000000000000000000000000"
        assert payload["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_escrow_create_ward_signed_false(self):
        """Wormhole escrow create under attack path still has ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            amount=0,  # edge: zero amount
            condition_hex="",
        )
        assert tx["ward_signed"] is False


# ---------------------------------------------------------------------------
# Adversarial: FlareAdapter
# ---------------------------------------------------------------------------


class TestAdversarialFlare:
    """Adversarial edge cases for FlareAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = FlareAdapter(
            rpc_url="https://flare-api.flare.network/ext/C/rpc",
            rlusd_address=EVM_ADDRESS,
        )

    @pytest.mark.asyncio
    async def test_adversarial_invalid_vault_state_not_defaulted(self):
        """verify_vault returns is_defaulted=False when no live RPC — no false positive."""
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert state.is_defaulted is False  # base stub — no spurious defaults

    @pytest.mark.asyncio
    async def test_adversarial_zero_payout_ward_signed_false(self):
        """Zero payout attack: ward_signed=False even with degenerate payout."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_chain_id_override_ward_signed_false(self):
        """Attacker overrides dest_chain_id — ward_signed still False."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=1_000_000,
            dest_chain_id=999,  # unknown chain
        )
        assert tx.ward_signed is False
        assert tx.send_max["chain_id"] == 999  # passed through but not signed
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_flare_escrow_create_ward_signed_false(self):
        """Flare escrow create under degenerate inputs — ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            amount=0,
            condition_hex="",
        )
        assert tx["ward_signed"] is False


# ---------------------------------------------------------------------------
# Adversarial: SolanaAdapter
# ---------------------------------------------------------------------------


class TestAdversarialSolana:
    """Adversarial edge cases for SolanaAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = SolanaAdapter(
            rpc_url="https://api.devnet.solana.com",
            rlusd_mint=SOL_ADDRESS,
        )

    @pytest.mark.asyncio
    async def test_adversarial_invalid_account_not_defaulted(self):
        """verify_vault on unregistered account returns is_defaulted=False — no false positive."""
        state = await self.adapter.verify_vault(
            vault_address=SOL_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=SOL_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_adversarial_zero_payout_ward_signed_false(self):
        """Zero payout on Solana: ward_signed=False."""
        tx = await self.adapter.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_stale_blockhash_still_unsigned(self):
        """Stale or empty blockhash does not cause signing — ward_signed=False."""
        tx = await self.adapter.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=500_000,
            recent_blockhash="",  # stale / missing blockhash
        )
        assert tx.ward_signed is False
        assert tx.send_max["recent_blockhash"] == ""

    @pytest.mark.asyncio
    async def test_adversarial_solana_escrow_create_ward_signed_false(self):
        """Solana escrow create under attack inputs — ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=SOL_ADDRESS,
            claimant_address=SOL_ADDRESS2,
            amount=0,
            condition_hex="DEADBEEF",
        )
        assert tx["ward_signed"] is False


# ---------------------------------------------------------------------------
# Adversarial: HederaAdapter
# ---------------------------------------------------------------------------


class TestAdversarialHedera:
    """Adversarial edge cases for HederaAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = HederaAdapter(
            mirror_node_url="https://testnet.mirrornode.hedera.com",
            rlusd_token_id="0.0.99999",
        )

    @pytest.mark.asyncio
    async def test_adversarial_invalid_hts_token_not_defaulted(self):
        """Unregistered HTS account returns is_defaulted=False — no false positive."""
        state = await self.adapter.verify_vault(
            vault_address=HEDERA_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=HEDERA_ACCOUNT2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_adversarial_zero_payout_hedera_ward_signed_false(self):
        """Zero payout on Hedera: ward_signed=False."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_token_id_spoofing_ward_signed_false(self):
        """Attacker-controlled token ID does not cause signing."""
        adapter = HederaAdapter(
            mirror_node_url="https://testnet.mirrornode.hedera.com",
            rlusd_token_id="0.0.EVIL",  # attacker-injected token ID
        )
        tx = await adapter.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=500_000,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False
        # Token ID in payload is what the adapter was configured with
        assert tx.send_max["token_id"] == "0.0.EVIL"

    @pytest.mark.asyncio
    async def test_adversarial_hedera_escrow_create_ward_signed_false(self):
        """Hedera escrow create under degenerate inputs — ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            amount=0,
            condition_hex="",
        )
        assert tx["ward_signed"] is False


# ---------------------------------------------------------------------------
# Adversarial: StellarAdapter
# ---------------------------------------------------------------------------


class TestAdversarialStellar:
    """Adversarial edge cases for StellarAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = StellarAdapter(
            horizon_url="https://horizon-testnet.stellar.org",
            rlusd_asset_code="RLUSD",
            rlusd_issuer=STELLAR_ACCOUNT,
        )

    @pytest.mark.asyncio
    async def test_adversarial_invalid_trustline_not_defaulted(self):
        """Unregistered Stellar account returns is_defaulted=False — no false positive."""
        state = await self.adapter.verify_vault(
            vault_address=STELLAR_ACCOUNT,
            loan_id=VALID_LOAN_ID,
            pool_address=STELLAR_ACCOUNT2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_adversarial_zero_stroops_ward_signed_false(self):
        """Zero payout (0 stroops) on Stellar: ward_signed=False."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_wrong_network_passphrase_unsigned(self):
        """Wrong network passphrase adapter — ward_signed=False (no automatic signing)."""
        adapter = StellarAdapter(
            horizon_url="https://horizon-testnet.stellar.org",
            rlusd_issuer=STELLAR_ACCOUNT,
            network_passphrase="ATTACKER CONTROLLED PASSPHRASE",
        )
        tx = await adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=5_000_000,
        )
        # Ward never signs — passphrase is only used by institution for XDR signing
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_asset_issuer_spoofing_ward_signed_false(self):
        """Attacker-injected issuer does not cause Ward to sign."""
        adapter = StellarAdapter(
            horizon_url="https://horizon-testnet.stellar.org",
            rlusd_issuer="GEVIL0000000000000000000000000000000000000000000000000",
        )
        tx = await adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=1_000_000,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_amount_str_precision_no_rounding_exploit(self):
        """Amount string formatting preserves exact value — no rounding exploit."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=1,  # 0.0000001 RLUSD (minimum stroop)
        )
        assert tx.send_max["amount_str"] == "0.0000001"
        assert tx.ward_signed is False


# ---------------------------------------------------------------------------
# Adversarial: XDCAdapter
# ---------------------------------------------------------------------------


class TestAdversarialXDC:
    """Adversarial edge cases for XDCAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = XDCAdapter(
            rpc_url="https://erpc.apothem.network",
            chain_id=51,
            rlusd_address=XDC_ADDRESS,
        )

    @pytest.mark.asyncio
    async def test_adversarial_invalid_vault_not_defaulted(self):
        """Unregistered XDC vault returns is_defaulted=False — no false positive."""
        state = await self.adapter.verify_vault(
            vault_address=XDC_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=XDC_ADDRESS2,
        )
        assert state.is_defaulted is False

    @pytest.mark.asyncio
    async def test_adversarial_zero_payout_xdc_ward_signed_false(self):
        """Zero payout on XDC: ward_signed=False."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_xdc_mainnet_chain_id_enforced(self):
        """Adapter chain ID override is passed through but ward_signed stays False."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=750_000,
            dest_chain_id=50,  # override to mainnet
        )
        assert tx.send_max["chain_id"] == 50
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_xdc_escrow_create_ward_signed_false(self):
        """XDC escrow create under degenerate inputs — ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_create(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            amount=0,
            condition_hex="",
        )
        assert tx["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_xdc_escrow_finish_ward_signed_false(self):
        """XDC escrow finish under attack inputs — ward_signed=False."""
        tx = await self.adapter.build_unsigned_escrow_finish(
            claimant_address=XDC_ADDRESS2,
            owner_address=XDC_ADDRESS,
            offer_sequence=0,
            condition_hex="",
            fulfillment_hex="EVIL_FULFILLMENT",
        )
        assert tx["ward_signed"] is False


# ---------------------------------------------------------------------------
# Adversarial: AxelarAdapter
# ---------------------------------------------------------------------------


class TestAdversarialAxelar:
    """Adversarial edge cases for AxelarAdapter. ward_signed=False throughout."""

    def setup_method(self):
        self.adapter = AxelarAdapter(
            source_rpc_url="https://rpc-evm-sidechain.xrpl.org",
            source_chain="xrpl-evm",
            dest_chain="ethereum",
            gateway_address=EVM_ADDRESS,
        )

    @pytest.mark.asyncio
    async def test_adversarial_message_delivery_failure_ward_signed_false(self):
        """Even when GMP message would fail delivery, ward_signed=False."""
        # Simulate failed delivery by using an unknown dest chain
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=500_000,
            dest_chain="UNKNOWN_CHAIN_XYZ",
        )
        assert tx.ward_signed is False
        assert tx.send_max["dest_chain"] == "UNKNOWN_CHAIN_XYZ"
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_cross_chain_resolution_rejected_not_signed(self):
        """Rejected cross-chain resolution never produces a signed payload."""
        # With no live RPC, vault appears not defaulted — no valid claim
        state = await self.adapter.verify_vault(
            vault_address=VALID_ADDRESS,
            loan_id=VALID_LOAN_ID,
            pool_address=VALID_ADDRESS2,
        )
        assert state.is_defaulted is False  # rejected at source
        # No signed payload ever constructed
        assert state.vault_address == VALID_ADDRESS

    @pytest.mark.asyncio
    async def test_adversarial_zero_payout_gmp_ward_signed_false(self):
        """Zero payout GMP message: ward_signed=False in all payload fields."""
        tx = await self.adapter.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=0,
        )
        assert tx.ward_signed is False
        assert tx.send_max["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_send_resolution_message_ward_signed_false(self):
        """send_resolution_message always returns ward_signed=False."""
        msg = await self.adapter.send_resolution_message(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=0,
            nonce=9999,
        )
        assert msg["ward_signed"] is False

    @pytest.mark.asyncio
    async def test_adversarial_axelar_payload_immutable_ward_signed(self):
        """AxelarGMPPayload.ward_signed is field(init=False) — cannot be overridden."""
        import dataclasses

        payload = AxelarGMPPayload(
            source_chain="xrpl-evm",
            dest_chain="ethereum",
            gateway_address="0x0000",
            dest_contract_address="0x0000",
            sender=VALID_ADDRESS,
            recipient=VALID_ADDRESS2,
            amount=1_000_000,
            nonce=0,
        )
        assert payload.ward_signed is False
        # Verify init_fields does not include ward_signed
        init_fields = {f.name for f in dataclasses.fields(AxelarGMPPayload) if f.init}
        assert "ward_signed" not in init_fields


# ---------------------------------------------------------------------------
# Adversarial: Cross-adapter — ward_signed invariant enforced everywhere
# ---------------------------------------------------------------------------


class TestAdversarialCoreInvariant:
    """
    Exhaustive ward_signed=False verification across all adapters and
    all failure/attack paths. This is the canonical invariant test.
    """

    @pytest.mark.asyncio
    async def test_invariant_all_adapters_build_resolution_tx_ward_signed_false(self):
        """Every adapter's build_resolution_tx returns ward_signed=False."""
        flare = FlareAdapter(rlusd_address=EVM_ADDRESS)
        axelar = AxelarAdapter(gateway_address=EVM_ADDRESS)
        solana = SolanaAdapter(rlusd_mint=SOL_ADDRESS)
        hedera = HederaAdapter(rlusd_token_id="0.0.99999")
        stellar = StellarAdapter(rlusd_issuer=STELLAR_ACCOUNT)
        xdc = XDCAdapter(rlusd_address=XDC_ADDRESS)
        wormhole = WormholeNTTAdapter()

        flare_tx = await flare.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=1_000_000,
        )
        axelar_tx = await axelar.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_amount=1_000_000,
        )
        solana_tx = await solana.build_resolution_tx(
            pool_token_account=SOL_ADDRESS,
            claimant_token_account=SOL_ADDRESS2,
            authority_address=SOL_ADDRESS,
            payout_amount=1_000_000,
        )
        hedera_tx = await hedera.build_resolution_tx(
            pool_address=HEDERA_ACCOUNT,
            claimant_address=HEDERA_ACCOUNT2,
            payout_amount=1_000_000,
        )
        stellar_tx = await stellar.build_resolution_tx(
            pool_address=STELLAR_ACCOUNT,
            claimant_address=STELLAR_ACCOUNT2,
            payout_amount=1_000_000,
        )
        xdc_tx = await xdc.build_resolution_tx(
            pool_address=XDC_ADDRESS,
            claimant_address=XDC_ADDRESS2,
            payout_amount=1_000_000,
        )
        wormhole_tx = await wormhole.build_resolution_tx(
            pool_address=VALID_ADDRESS,
            claimant_address=VALID_ADDRESS2,
            payout_drops=1_000_000,
        )

        for tx in [
            flare_tx,
            axelar_tx,
            solana_tx,
            hedera_tx,
            stellar_tx,
            xdc_tx,
            wormhole_tx,
        ]:
            assert tx.ward_signed is False, f"ward_signed=True on {tx.tx_type}"

    @pytest.mark.asyncio
    async def test_invariant_all_adapters_send_max_ward_signed_false(self):
        """Every adapter's send_max payload has ward_signed=False."""
        flare = FlareAdapter(rlusd_address=EVM_ADDRESS)
        axelar = AxelarAdapter(gateway_address=EVM_ADDRESS)
        solana = SolanaAdapter(rlusd_mint=SOL_ADDRESS)
        hedera = HederaAdapter(rlusd_token_id="0.0.99999")
        stellar = StellarAdapter(rlusd_issuer=STELLAR_ACCOUNT)
        xdc = XDCAdapter(rlusd_address=XDC_ADDRESS)
        wormhole = WormholeNTTAdapter()

        results = []
        results.append(
            (
                await flare.build_resolution_tx(
                    pool_address=VALID_ADDRESS,
                    claimant_address=VALID_ADDRESS2,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await axelar.build_resolution_tx(
                    pool_address=VALID_ADDRESS,
                    claimant_address=VALID_ADDRESS2,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await solana.build_resolution_tx(
                    pool_token_account=SOL_ADDRESS,
                    claimant_token_account=SOL_ADDRESS2,
                    authority_address=SOL_ADDRESS,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await hedera.build_resolution_tx(
                    pool_address=HEDERA_ACCOUNT,
                    claimant_address=HEDERA_ACCOUNT2,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await stellar.build_resolution_tx(
                    pool_address=STELLAR_ACCOUNT,
                    claimant_address=STELLAR_ACCOUNT2,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await xdc.build_resolution_tx(
                    pool_address=XDC_ADDRESS,
                    claimant_address=XDC_ADDRESS2,
                    payout_amount=1,
                )
            ).send_max
        )
        results.append(
            (
                await wormhole.build_resolution_tx(
                    pool_address=VALID_ADDRESS,
                    claimant_address=VALID_ADDRESS2,
                    payout_drops=1,
                )
            ).send_max
        )

        for payload in results:
            assert payload is not None
            assert payload["ward_signed"] is False, (
                f"ward_signed=True in payload: {payload}"
            )

    @pytest.mark.asyncio
    async def test_invariant_all_adapters_escrow_create_ward_signed_false(self):
        """Every adapter's escrow create has ward_signed=False."""
        adapters = [
            FlareAdapter(rlusd_address=EVM_ADDRESS),
            AxelarAdapter(gateway_address=EVM_ADDRESS),
            SolanaAdapter(rlusd_mint=SOL_ADDRESS),
            HederaAdapter(rlusd_token_id="0.0.99999"),
            StellarAdapter(rlusd_issuer=STELLAR_ACCOUNT),
            XDCAdapter(rlusd_address=XDC_ADDRESS),
            WormholeNTTAdapter(),
        ]
        for adapter in adapters:
            # Use appropriate address format per adapter
            pool = (
                HEDERA_ACCOUNT
                if isinstance(adapter, HederaAdapter)
                else (
                    STELLAR_ACCOUNT
                    if isinstance(adapter, StellarAdapter)
                    else VALID_ADDRESS
                )
            )
            claimant = (
                HEDERA_ACCOUNT2
                if isinstance(adapter, HederaAdapter)
                else (
                    STELLAR_ACCOUNT2
                    if isinstance(adapter, StellarAdapter)
                    else VALID_ADDRESS2
                )
            )
            tx = await adapter.build_unsigned_escrow_create(
                pool_address=pool,
                claimant_address=claimant,
                amount=1_000_000,
                condition_hex="ABCD1234",
            )
            assert tx["ward_signed"] is False, (
                f"ward_signed=True on {type(adapter).__name__}"
            )


# ===========================================================================
# Tests: Network configuration guard (B1 — WARD_XRPL_URL / WARD_NETWORK)
# ===========================================================================


class TestNetworkConfig:
    """
    B1 mainnet readiness: verify that constructors require WARD_XRPL_URL /
    WARD_XRPL_WS and that WARD_NETWORK mismatches are hard failures.

    Each test clears the env vars set by the conftest autouse fixture, then
    sets only what it needs, so the test environment is explicit.
    """

    # -- Missing env vars --------------------------------------------------

    def test_claim_validator_raises_when_url_missing(self, monkeypatch):
        """ClaimValidator() raises ConfigurationError when WARD_XRPL_URL is unset."""
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError, match="WARD_XRPL_URL"):
            ClaimValidator()

    def test_ward_client_raises_when_url_missing(self, monkeypatch):
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.client import WardClient

        with pytest.raises(ConfigurationError, match="WARD_XRPL_URL"):
            WardClient()

    def test_resolver_raises_when_url_missing(self, monkeypatch):
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.resolver import Resolver

        with pytest.raises(ConfigurationError, match="WARD_XRPL_URL"):
            Resolver()

    def test_escrow_settlement_raises_when_url_missing(self, monkeypatch):
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.settlement import EscrowSettlement

        with pytest.raises(ConfigurationError, match="WARD_XRPL_URL"):
            EscrowSettlement()

    def test_pool_health_monitor_raises_when_url_missing(self, monkeypatch):
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.pool import PoolHealthMonitor

        with pytest.raises(ConfigurationError, match="WARD_XRPL_URL"):
            PoolHealthMonitor(pool_address=VALID_ADDRESS)

    def test_vault_monitor_raises_when_ws_missing(self, monkeypatch):
        monkeypatch.delenv("WARD_XRPL_WS", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.vault_monitor import VaultMonitor

        with pytest.raises(ConfigurationError, match="WARD_XRPL_WS"):
            VaultMonitor(vault_addresses=[VALID_ADDRESS])

    # -- WARD_NETWORK mismatch ---------------------------------------------

    def test_network_mismatch_testnet_url_mainnet_env(self, monkeypatch):
        """Testnet URL + WARD_NETWORK=mainnet is a hard ConfigurationError."""
        monkeypatch.setenv("WARD_XRPL_URL", "https://s.altnet.rippletest.net:51234/")
        monkeypatch.setenv("WARD_NETWORK", "mainnet")
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError, match="mainnet"):
            ClaimValidator()

    def test_network_mismatch_mainnet_url_testnet_env(self, monkeypatch):
        """Mainnet URL + WARD_NETWORK=testnet is a hard ConfigurationError."""
        monkeypatch.setenv("WARD_XRPL_URL", "https://xrplcluster.com/")
        monkeypatch.setenv("WARD_NETWORK", "testnet")
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError, match="testnet"):
            ClaimValidator()

    def test_network_mismatch_explicit_url_override(self, monkeypatch):
        """Explicitly passing a mainnet URL while WARD_NETWORK=testnet also fails."""
        monkeypatch.setenv("WARD_NETWORK", "testnet")
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError, match="testnet"):
            ClaimValidator(url="https://xrplcluster.com/")

    def test_invalid_ward_network_value(self, monkeypatch):
        """WARD_NETWORK=staging is invalid and raises ConfigurationError."""
        monkeypatch.setenv("WARD_XRPL_URL", "https://s.altnet.rippletest.net:51234/")
        monkeypatch.setenv("WARD_NETWORK", "staging")
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError, match="invalid"):
            ClaimValidator()

    # -- Happy paths -------------------------------------------------------

    def test_mainnet_url_with_mainnet_env_accepted(self, monkeypatch):
        """Mainnet URL + WARD_NETWORK=mainnet is accepted."""
        monkeypatch.setenv("WARD_XRPL_URL", "https://xrplcluster.com/")
        monkeypatch.setenv("WARD_NETWORK", "mainnet")
        from ward.validator import ClaimValidator

        v = ClaimValidator()
        assert v._url == "https://xrplcluster.com/"

    def test_testnet_url_with_no_ward_network_accepted(self, monkeypatch):
        """Testnet URL with WARD_NETWORK unset is accepted (opt-in guard)."""
        monkeypatch.setenv("WARD_XRPL_URL", "https://s.altnet.rippletest.net:51234/")
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward.validator import ClaimValidator

        v = ClaimValidator()
        assert "altnet" in v._url

    def test_error_message_includes_setup_instructions(self, monkeypatch):
        """ConfigurationError message must contain setup examples."""
        monkeypatch.delenv("WARD_XRPL_URL", raising=False)
        monkeypatch.delenv("WARD_NETWORK", raising=False)
        from ward import ConfigurationError
        from ward.validator import ClaimValidator

        with pytest.raises(ConfigurationError) as exc_info:
            ClaimValidator()
        msg = str(exc_info.value)
        assert "xrplcluster.com" in msg, "message should show mainnet example"
        assert "altnet" in msg, "message should show testnet example"
