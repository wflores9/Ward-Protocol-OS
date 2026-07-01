"""
Ward Protocol — Coverage gap tests for critical modules.

Targets modules below 85%:
  ward/primitives.py  (77%) — validate_condition_hex, validate_wallet,
                              get_ledger_close_time fallbacks, rate-limit eviction
  ward/validator.py   (79%) — step helpers, LedgerError path, metadata parsing
  ward/settlement.py  (81%) — Redis lock duplicate, cancel_escrow tx-build path
"""
from __future__ import annotations

import asyncio
import collections
import json
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ward.primitives import (
    LedgerError,
    ValidationError,
    validate_condition_hex,
    validate_loan_id,
    validate_wallet,
)
from ward.settlement import EscrowRecord, EscrowSettlement
from ward.validator import ClaimValidator

_VALID_A = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
_VALID_B = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
_NFT_ID  = "A" * 64   # 64 uppercase hex chars — passes validate_nft_id
_LOAN_ID = "A" * 64   # 64 hex chars — passes validate_loan_id


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@asynccontextmanager
async def _null_ctx(*a, **kw):
    """Async context manager that yields a MagicMock client."""
    yield MagicMock()


# ---------------------------------------------------------------------------
# ward/primitives.py
# ---------------------------------------------------------------------------


class TestPrimitivesGaps:

    # validate_loan_id — empty / non-string (line 205)

    def test_validate_loan_id_empty_raises(self):
        with pytest.raises(ValidationError, match="non-empty"):
            validate_loan_id("")

    def test_validate_loan_id_none_raises(self):
        with pytest.raises(ValidationError):
            validate_loan_id(None)  # type: ignore[arg-type]

    # validate_condition_hex — four distinct error branches
    # (lines 415, 418, 423-424, 426)

    def test_condition_hex_non_string_raises(self):
        with pytest.raises(ValidationError, match="must be a string"):
            validate_condition_hex(12345)  # type: ignore[arg-type]

    def test_condition_hex_wrong_length_raises(self):
        # 80 hex chars — should fail the == 78 check
        bad = "A0258020" + "00" * 32 + "810120" + "FF"
        with pytest.raises(ValidationError, match="78 hex chars"):
            validate_condition_hex(bad)

    def test_condition_hex_invalid_chars_raises(self):
        # 78 chars but 'Z' is not valid hex
        with pytest.raises(ValidationError, match="invalid hex"):
            validate_condition_hex("Z" * 78)

    def test_condition_hex_wrong_prefix_raises(self):
        # 78 valid uppercase hex chars but wrong ASN.1 prefix
        bad = "FFFF8020" + "00" * 32 + "810120"
        with pytest.raises(ValidationError, match="prefix"):
            validate_condition_hex(bad)

    # validate_wallet — non-Wallet input (lines 309-314)

    def test_validate_wallet_string_raises(self):
        with pytest.raises(ValidationError, match="xrpl.wallet.Wallet"):
            validate_wallet("seed-string-not-a-wallet")

    def test_validate_wallet_dict_raises(self):
        with pytest.raises(ValidationError):
            validate_wallet({"classic_address": _VALID_A})  # type: ignore[arg-type]

    def test_validate_wallet_none_raises(self):
        with pytest.raises(ValidationError):
            validate_wallet(None)  # type: ignore[arg-type]

    # get_ledger_close_time — success and fallback paths (lines 342-344, 353-356)

    def test_ledger_close_time_from_ledger_request(self):
        """Ledger(validated) succeeds on first try — covers lines 342-344."""
        from ward.primitives import get_ledger_close_time

        ok_resp = MagicMock()
        ok_resp.is_successful.return_value = True
        ok_resp.result = {"ledger": {"close_time": 850_000_000}}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=ok_resp)

        result = _run(get_ledger_close_time(mock_client))
        assert result == 850_000_000

    def test_ledger_close_time_fallback_to_server_info(self):
        """Ledger fails → fallback to ServerInfo succeeds — covers lines 353-356."""
        from ward.primitives import get_ledger_close_time

        fail_resp = MagicMock()
        fail_resp.is_successful.return_value = False

        ok_resp = MagicMock()
        ok_resp.is_successful.return_value = True
        ok_resp.result = {"info": {"validated_ledger": {"close_time": 800_000_000}}}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=[fail_resp, ok_resp])

        result = _run(get_ledger_close_time(mock_client))
        assert result == 800_000_000

    def test_ledger_close_time_both_fail_raises_ledger_error(self):
        """Both Ledger and ServerInfo fail → LedgerError raised."""
        from ward.primitives import get_ledger_close_time

        fail_resp = MagicMock()
        fail_resp.is_successful.return_value = False

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=fail_resp)

        with pytest.raises(LedgerError):
            _run(get_ledger_close_time(mock_client))

    def test_ledger_close_time_first_request_exception_fallback(self):
        """First request throws exception → falls back to ServerInfo."""
        from ward.primitives import get_ledger_close_time

        ok_resp = MagicMock()
        ok_resp.is_successful.return_value = True
        ok_resp.result = {"info": {"validated_ledger": {"close_time": 760_000_000}}}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=[Exception("connection refused"), ok_resp]
        )

        result = _run(get_ledger_close_time(mock_client))
        assert result == 760_000_000

    # check_rate_limit — eviction when dict grows too large (lines 290-296)

    def test_rate_limit_dict_eviction(self):
        """Oldest entries are evicted when _rate_limit_windows exceeds the cap."""
        import ward.primitives as _p

        orig_windows = dict(_p._rate_limit_windows)
        orig_max     = _p._MAX_RATE_LIMIT_ENTRIES
        orig_evict   = _p._RATE_LIMIT_EVICT_COUNT
        try:
            now = time.monotonic()
            _p._rate_limit_windows = {
                f"evict-key-{i}": collections.deque([now]) for i in range(4)
            }
            _p._MAX_RATE_LIMIT_ENTRIES = 4
            _p._RATE_LIMIT_EVICT_COUNT = 1
            # Adding a 5th entry → len becomes 5 > 4 → one entry evicted
            _p.check_rate_limit("evict-trigger-token")
            assert len(_p._rate_limit_windows) <= 4
        finally:
            _p._rate_limit_windows = orig_windows
            _p._MAX_RATE_LIMIT_ENTRIES = orig_max
            _p._RATE_LIMIT_EVICT_COUNT = orig_evict


# ---------------------------------------------------------------------------
# ward/validator.py
# ---------------------------------------------------------------------------


class TestValidatorGaps:

    # _parse_nft_metadata — five edge-case branches
    # (lines 263, 271, 274, 276-277)

    def test_parse_nft_metadata_no_uri(self):
        meta, err = ClaimValidator._parse_nft_metadata({})
        assert err == "NFT has no URI field"
        assert meta == {}

    def test_parse_nft_metadata_uri_too_long(self):
        meta, err = ClaimValidator._parse_nft_metadata({"URI": "A" * 513})
        assert err is not None
        assert "512" in err

    def test_parse_nft_metadata_invalid_hex(self):
        meta, err = ClaimValidator._parse_nft_metadata({"URI": "ZZ"})
        assert err is not None
        assert "Metadata parse error" in err

    def test_parse_nft_metadata_unknown_ward_schema(self):
        data = json.dumps({"w": "not-ward"}).encode()
        meta, err = ClaimValidator._parse_nft_metadata({"URI": data.hex()})
        assert err is not None
        assert "Unknown URI schema" in err

    def test_parse_nft_metadata_unknown_protocol(self):
        data = json.dumps({"protocol": "other-v1"}).encode()
        meta, err = ClaimValidator._parse_nft_metadata({"URI": data.hex()})
        assert err is not None
        assert "Unknown protocol" in err

    # _step3_verify_vault_binding — vault mismatch

    def test_step3_vault_mismatch_rejected(self):
        err = ClaimValidator._step3_verify_vault_binding(
            {"vault_address": _VALID_A}, _VALID_B
        )
        assert err is not None
        assert "Cross-vault claim rejected" in err

    def test_step3_missing_vault_in_metadata(self):
        err = ClaimValidator._step3_verify_vault_binding({}, _VALID_B)
        assert err is not None

    # _step6_check_coverage_breach — pool None, insolvent, insufficient
    # (lines 384, 391-400)

    def test_step6_pool_none_returns_error(self):
        v = ClaimValidator(_VALID_A)
        err, breached = v._step6_check_coverage_breach(None, _VALID_A)
        assert "Pool AccountInfo failed" in err
        assert breached is False

    def test_step6_insolvent_pool_returns_true(self):
        v = ClaimValidator(_VALID_A)
        # OwnerCount=100 → reserve = 10M + 100*2M = 210M > balance 1000
        pool_info = {"Balance": "1000", "OwnerCount": "100"}
        err, breached = v._step6_check_coverage_breach(pool_info, _VALID_A)
        assert err is not None
        assert breached is True

    def test_step6_insufficient_balance_for_payout(self):
        v = ClaimValidator(_VALID_A)
        # Solvent but not enough to cover the claimed min_balance
        pool_info = {"Balance": "20000000", "OwnerCount": "0"}
        err, breached = v._step6_check_coverage_breach(
            pool_info, _VALID_A, min_balance=50_000_000
        )
        assert err is not None
        assert "insufficient balance" in err
        assert breached is False

    def test_step6_healthy_pool_returns_none(self):
        v = ClaimValidator(_VALID_A)
        pool_info = {"Balance": "100000000", "OwnerCount": "0"}
        err, breached = v._step6_check_coverage_breach(pool_info, _VALID_A)
        assert err is None
        assert breached is False

    # _step7_verify_nft_live — NFT burned / taxon mismatch (line 413)

    def test_step7_nft_none_returns_error(self):
        v = ClaimValidator(_VALID_A)
        result = _run(v._step7_verify_nft_live(None, _NFT_ID))
        assert result is not None
        assert "burned" in result.lower() or "Replay" in result

    # _step8_verify_claimant_holds_nft — claimant doesn't hold

    def test_step8_nft_none_returns_error(self):
        v = ClaimValidator(_VALID_A)
        result = _run(v._step8_verify_claimant_holds_nft(None, _VALID_A, _NFT_ID))
        assert result is not None
        assert "does not currently hold" in result

    # _step9_check_pool_solvency — pool None, low balance, low ratio
    # (lines 462, 469)

    def test_step9_pool_none_returns_error(self):
        v = ClaimValidator(_VALID_A)
        err = v._step9_check_pool_solvency(None, 1_000_000)
        assert "unavailable" in err

    def test_step9_path_unavailable_returns_error(self):
        v = ClaimValidator(_VALID_A)
        pool_info = {"Balance": "100000000", "OwnerCount": "0"}
        err = v._step9_check_pool_solvency(pool_info, 1_000_000, path_available=False)
        assert "cross-asset" in err.lower() or "path" in err.lower()

    def test_step9_usable_below_payout_returns_error(self):
        v = ClaimValidator(_VALID_A)
        pool_info = {"Balance": "1000", "OwnerCount": "0"}
        err = v._step9_check_pool_solvency(pool_info, 5_000_000)
        assert err is not None
        assert "insolvent" in err.lower()

    def test_step9_ratio_below_minimum_returns_error(self):
        v = ClaimValidator(_VALID_A)
        # XRPL_BASE_RESERVE_DROPS = 20_000_000; OwnerCount = 0
        # usable = 26_000_000 - 20_000_000 = 6_000_000
        # payout = 5_000_000; ratio = 6/5 = 1.2 < MIN_COVERAGE_RATIO (1.5)
        pool_info = {"Balance": "26000000", "OwnerCount": "0"}
        err = v._step9_check_pool_solvency(pool_info, 5_000_000)
        assert err is not None
        assert "ratio" in err.lower()

    # _reject — rejection_memo_hex encoded correctly

    def test_reject_memo_hex_is_valid_json(self):
        result = ClaimValidator._reject(3, "test vault mismatch")
        assert result.rejection_memo_hex != ""
        decoded = bytes.fromhex(result.rejection_memo_hex).decode("utf-8")
        data = json.loads(decoded)
        assert data["ward_reject"] is True
        assert data["step"] == 3
        assert data["reason"] == "test vault mismatch"

    # _fetch_pool_info — unsuccessful response and exception (lines 469, 471-473)

    def test_fetch_pool_info_unsuccessful_returns_none(self):
        v = ClaimValidator(_VALID_A)
        fail_resp = MagicMock()
        fail_resp.is_successful.return_value = False
        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=fail_resp)

        result = _run(v._fetch_pool_info(mock_client, _VALID_A))
        assert result is None

    def test_fetch_pool_info_exception_returns_none(self):
        v = ClaimValidator(_VALID_A)
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=Exception("network failure"))

        result = _run(v._fetch_pool_info(mock_client, _VALID_A))
        assert result is None

    # _step2_verify_premium_payment — coverage_drops <= 0 (line 301)

    def test_step2_premium_zero_coverage_rejects(self):
        v = ClaimValidator(_VALID_A)

        async def run():
            return await v._step2_verify_premium_payment(
                client=MagicMock(),
                claimant_address=_VALID_A,
                pool_address=_VALID_B,
                nft_token_id=_NFT_ID,
                coverage_drops=0,
            )

        result = _run(run())
        assert result is not None
        assert "coverage" in result.lower() or "missing" in result.lower()

    def test_step2_premium_client_exception_rejects(self):
        v = ClaimValidator(_VALID_A)
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=Exception("rpc error"))

        async def run():
            return await v._step2_verify_premium_payment(
                client=mock_client,
                claimant_address=_VALID_A,
                pool_address=_VALID_B,
                nft_token_id=_NFT_ID,
                coverage_drops=1_000_000,
            )

        result = _run(run())
        assert result is not None
        assert "failed" in result.lower() or "error" in result.lower()

    # validate_claim — LedgerError caught and returned as ValidationResult
    # (lines 211-213)

    def test_validate_claim_ledger_error_returns_failed_result(self):
        async def run():
            with patch("ward.validator.client_context", _null_ctx), patch.object(
                ClaimValidator,
                "_step1_verify_nft_exists",
                AsyncMock(side_effect=LedgerError("simulated timeout")),
            ):
                v = ClaimValidator("http://localhost")
                return await v.validate_claim(
                    claimant_address=_VALID_A,
                    nft_token_id=_NFT_ID,
                    defaulted_vault=_VALID_B,
                    loan_id=_LOAN_ID,
                    pool_address=_VALID_A,
                )

        result = _run(run())
        assert not result.approved
        assert "Ledger error" in result.rejection_reason


# ---------------------------------------------------------------------------
# ward/settlement.py
# ---------------------------------------------------------------------------


class TestSettlementGaps:

    def _make_record(self, *, cancel_after: int = 800_100_000) -> EscrowRecord:
        return EscrowRecord(
            claim_id="gap-claim-1",
            nft_token_id=_NFT_ID,
            pool_address=_VALID_A,
            claimant_address=_VALID_B,
            payout_drops=1_000_000,
            escrow_sequence=42,
            condition_hex="00" * 32,
            tx_hash="B" * 64,
            dispute_deadline_ripple=800_050_000,
            cancel_after_ripple=cancel_after,
        )

    # finish_escrow — Redis duplicate-settlement lock (lines 206-221)

    def test_finish_escrow_duplicate_rejected(self):
        """Redis lock not acquired → ValidationError raised immediately."""
        import ward.settlement as _sm

        record = self._make_record()

        mock_redis = MagicMock()
        mock_redis.set.return_value = None  # None = lock already held

        async def run():
            with patch.object(_sm, "_settlement_redis", mock_redis):
                s = EscrowSettlement()
                return await s.finish_escrow(
                    pool_address=_VALID_A,
                    claimant_address_signer=_VALID_B,
                    escrow_record=record,
                    fulfillment_hex="A0" * 36,
                )

        with pytest.raises(ValidationError, match="Duplicate settlement"):
            _run(run())

    def test_finish_escrow_redis_exception_proceeds(self):
        """Redis raises an unexpected exception → proceeds without lock (fail-open)."""
        import ward.settlement as _sm

        record = self._make_record()

        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("redis connection error")

        async def run():
            with patch.object(_sm, "_settlement_redis", mock_redis), \
                 patch("ward.settlement.client_context", _null_ctx), \
                 patch("ward.settlement.get_ledger_close_time",
                       new=AsyncMock(return_value=800_000_000)), \
                 patch("ward.settlement.autofill",
                       new=AsyncMock(side_effect=lambda tx, c: tx)), \
                 patch("ward.settlement.build_unsigned_tx",
                       new=AsyncMock(return_value=None)):
                s = EscrowSettlement()
                return await s.finish_escrow(
                    pool_address=_VALID_A,
                    claimant_address_signer=_VALID_B,
                    escrow_record=record,
                    fulfillment_hex="A0" * 36,
                )

        result = _run(run())
        assert result["ward_signed"] == "false"

    # cancel_escrow — transaction-build path after window opens (lines 302-322)

    def test_cancel_escrow_past_window_returns_unsigned(self):
        """cancel_escrow after cancel_after_ripple builds EscrowCancel unsigned tx."""
        record = self._make_record(cancel_after=800_100_000)

        async def run():
            with patch("ward.settlement.client_context", _null_ctx), \
                 patch("ward.settlement.get_ledger_close_time",
                       new=AsyncMock(return_value=800_200_000)), \
                 patch("ward.settlement.autofill",
                       new=AsyncMock(side_effect=lambda tx, c: tx)), \
                 patch("ward.settlement.build_unsigned_tx",
                       new=AsyncMock(return_value=None)):
                s = EscrowSettlement()
                return await s.cancel_escrow(_VALID_A, record, "policy expired")

        result = _run(run())
        assert result == "unsigned"
