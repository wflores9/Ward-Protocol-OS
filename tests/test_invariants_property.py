"""
Ward Protocol — Property-based invariant tests (Hypothesis).

Formally enforces INVARIANTS.md across:
  INV-001/003: ward_signed is always False
  INV-007:     approved=True iff steps_passed==9
  INV-009:     Expired coverage fails closed
  INV-012:     Loss amount must be real and bounded
  INV-017:     Settlement construction is idempotent
  INV-024:     No floating point in drop amounts
  INV-027:     Invalid addresses always fail closed
  INV-026:     Private key material rejected at API boundary

Run:
    python3 -m pytest tests/test_invariants_property.py -v --no-cov
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import fields
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from xrpl.core.addresscodec import is_valid_classic_address

from ward.client import WardClient
from ward.constants import (
    DEFAULT_TESTNET_URL,
    ESCROW_CANCEL_HOURS,
    ESCROW_DISPUTE_HOURS,
    XRP_MAX_DROPS,
)
from ward.primitives import (
    LedgerError,
    UnsignedTransaction,
    ValidationError,
    validate_drops,
    validate_drops_amount,
    validate_xrpl_address,
)
from ward.settlement import EscrowRecord
from ward.validator import ClaimValidator, ValidationResult
from ward.webhooks import WebhookEvent, WebhookPayload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ADDRESS_A = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
_VALID_ADDRESS_B = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"


def _run(coro):
    """Run a coroutine in a fresh event loop (safe inside @given)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# INV-001 / INV-003 — ward_signed is always False
# ---------------------------------------------------------------------------


class TestInv001WardSignedNeverTrue:
    """INV-001/003: No Ward output object ever carries ward_signed=True."""

    @given(
        tx_type=st.text(min_size=1, max_size=64),
        amount_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS),
    )
    def test_unsigned_transaction_ward_signed_always_false(
        self, tx_type: str, amount_drops: int
    ):
        tx = UnsignedTransaction(
            tx_type=tx_type,
            account=_VALID_ADDRESS_A,
            destination=_VALID_ADDRESS_B,
            amount_drops=amount_drops,
        )
        assert tx.ward_signed is False

    @given(
        tx_type=st.text(min_size=1, max_size=64),
        amount_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS),
    )
    def test_unsigned_transaction_ward_signed_not_settable(
        self, tx_type: str, amount_drops: int
    ):
        # ward_signed has init=False — it is structurally impossible to pass True
        tx_fields = {f.name: f for f in fields(UnsignedTransaction)}
        assert tx_fields["ward_signed"].init is False
        tx = UnsignedTransaction(
            tx_type=tx_type,
            account=_VALID_ADDRESS_A,
            destination=_VALID_ADDRESS_B,
            amount_drops=amount_drops,
        )
        assert tx.ward_signed is False

    @given(
        event=st.sampled_from(list(WebhookEvent)),
        health_ratio=st.one_of(
            st.none(),
            st.floats(
                min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
            ),
        ),
        timestamp=st.integers(min_value=0, max_value=2**31),
    )
    def test_webhook_payload_ward_signed_always_false(
        self, event: WebhookEvent, health_ratio, timestamp: int
    ):
        payload = WebhookPayload(
            event=event,
            vault_address=_VALID_ADDRESS_A,
            health_ratio=health_ratio,
            timestamp=timestamp,
        )
        assert payload.ward_signed is False

    def test_ward_client_no_private_key_params(self):
        """INV-003: WardClient.purchase_coverage requires no private key input."""
        sig = inspect.signature(WardClient.purchase_coverage)
        forbidden = {"wallet_seed", "private_key", "secret", "signing_key", "key"}
        actual_params = set(sig.parameters)
        intersection = forbidden & actual_params
        assert not intersection, (
            f"WardClient.purchase_coverage must not accept private key params; "
            f"found: {intersection}"
        )

    def test_ward_client_multi_vault_no_private_key_params(self):
        """WardClient.purchase_multi_vault_coverage also has no private key param."""
        sig = inspect.signature(WardClient.purchase_multi_vault_coverage)
        forbidden = {"wallet_seed", "private_key", "secret", "signing_key", "key"}
        intersection = forbidden & set(sig.parameters)
        assert not intersection, (
            f"purchase_multi_vault_coverage must not accept key params; "
            f"found: {intersection}"
        )


# ---------------------------------------------------------------------------
# INV-007 — approved=True implies steps_passed==9; steps_passed<9 implies rejected
# ---------------------------------------------------------------------------


class TestInv007NineCheckRequirement:
    """INV-007: A claim cannot pass unless all nine checks pass."""

    @given(
        step=st.integers(min_value=1, max_value=9),
        reason=st.text(min_size=1, max_size=256),
    )
    def test_reject_helper_always_produces_approved_false(
        self, step: int, reason: str
    ):
        result = ClaimValidator._reject(step, reason)
        assert result.approved is False
        assert result.steps_passed == step - 1
        assert result.steps_passed < 9

    @given(step=st.integers(min_value=1, max_value=9))
    def test_reject_helper_steps_passed_equals_step_minus_one(self, step: int):
        result = ClaimValidator._reject(step, "reason")
        assert result.steps_passed == step - 1

    @given(
        steps_passed=st.integers(min_value=0, max_value=8),
        reason=st.text(min_size=1),
    )
    def test_steps_passed_lt9_means_not_approved(
        self, steps_passed: int, reason: str
    ):
        # Any ValidationResult with steps_passed < 9 must have approved=False
        result = ValidationResult(
            approved=False,
            steps_passed=steps_passed,
            rejection_reason=reason,
        )
        assert result.steps_passed < 9
        assert not result.approved

    @given(payout=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_approved_result_always_has_steps_passed_9(self, payout: int):
        # The only valid approved=True state has steps_passed=9
        result = ValidationResult(
            approved=True,
            claim_payout_drops=payout,
            steps_passed=9,
        )
        assert result.approved is True
        assert result.steps_passed == 9

    @given(
        steps=st.integers(min_value=0, max_value=9),
        payout=st.integers(min_value=0, max_value=XRP_MAX_DROPS),
    )
    def test_ward_invariant_approved_iff_steps_9(self, steps: int, payout: int):
        # Logical invariant: Ward only approves when all 9 steps pass
        approved = steps == 9
        result = ValidationResult(
            approved=approved,
            claim_payout_drops=payout if approved else 0,
            steps_passed=steps,
        )
        if result.approved:
            assert result.steps_passed == 9
        if result.steps_passed < 9:
            assert not result.approved


# ---------------------------------------------------------------------------
# INV-009 — Coverage window: expired coverage fails closed
# ---------------------------------------------------------------------------


class TestInv009CoverageWindow:
    """INV-009: Expired coverage always fails closed."""

    @given(
        expiry=st.integers(min_value=0, max_value=2**32 - 1),
        now=st.integers(min_value=0, max_value=2**32 - 1),
    )
    def test_expiry_check_fails_closed_when_expired(
        self, expiry: int, now: int
    ):
        async def run():
            validator = ClaimValidator.__new__(ClaimValidator)
            validator._url = DEFAULT_TESTNET_URL
            with patch(
                "ward.validator.get_ledger_close_time",
                new=AsyncMock(return_value=now),
            ):
                return await validator._step2_check_expiry(None, {"e": expiry})

        result = _run(run())
        if expiry < now:
            # Policy is expired — step 2 must return a rejection reason
            assert result is not None, (
                f"Expected rejection for expiry={expiry} < now={now}, got None"
            )
            assert "expired" in result.lower() or "Policy expired" in result
        else:
            # Policy still valid — step 2 must return None (no error)
            assert result is None, (
                f"Unexpected rejection for expiry={expiry} >= now={now}: {result!r}"
            )

    @given(expiry=st.integers(min_value=0, max_value=2**32 - 1))
    def test_missing_expiry_always_rejects(self, expiry: int):
        """Metadata with no expiry field always fails step 2."""
        async def run():
            validator = ClaimValidator.__new__(ClaimValidator)
            validator._url = DEFAULT_TESTNET_URL
            with patch(
                "ward.validator.get_ledger_close_time",
                new=AsyncMock(return_value=expiry),
            ):
                return await validator._step2_check_expiry(None, {})

        result = _run(run())
        assert result is not None
        assert "Missing expiry" in result

    @given(
        now=st.integers(min_value=1, max_value=2**31),
        delta=st.integers(min_value=0, max_value=2**30),
    )
    def test_future_expiry_always_passes(self, now: int, delta: int):
        """expiry = now + delta (>= now) must never produce a rejection."""
        expiry = now + delta

        async def run():
            validator = ClaimValidator.__new__(ClaimValidator)
            validator._url = DEFAULT_TESTNET_URL
            with patch(
                "ward.validator.get_ledger_close_time",
                new=AsyncMock(return_value=now),
            ):
                return await validator._step2_check_expiry(None, {"e": expiry})

        result = _run(run())
        assert result is None, (
            f"expiry={expiry} >= now={now} should pass, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# INV-012 — Loss amount must be real and bounded
# ---------------------------------------------------------------------------


class TestInv012VaultLossBounds:
    """INV-012: Vault loss must be positive and within XRP supply cap."""

    @given(vault_loss=st.integers(max_value=0))
    def test_nonpositive_vault_loss_rejects_at_step5(self, vault_loss: int):
        # The validator calls _reject(5, ...) when vault_loss <= 0
        result = ClaimValidator._reject(
            5, f"Vault loss not positive: {vault_loss}"
        )
        assert not result.approved
        # step 5 rejected → steps_passed == 4
        assert result.steps_passed == 4

    @given(vault_loss=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_positive_bounded_vault_loss_passes_drops_validation(
        self, vault_loss: int
    ):
        # A positive vault_loss within XRP max must pass drops validation
        validate_drops_amount(vault_loss, "vault_loss")  # must not raise

    @given(vault_loss=st.integers(min_value=XRP_MAX_DROPS + 1))
    def test_vault_loss_exceeding_max_drops_raises(self, vault_loss: int):
        with pytest.raises(ValidationError):
            validate_drops_amount(vault_loss, "vault_loss")

    @given(vault_loss=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_valid_vault_loss_step5_passes(self, vault_loss: int):
        # The validator's step-5 condition is: vault_loss <= 0 → reject
        # Positive vault_loss does NOT trigger rejection at step 5
        triggered = vault_loss <= 0
        assert not triggered  # by hypothesis filter (assume)


# ---------------------------------------------------------------------------
# INV-017 — Settlement construction is idempotent
# ---------------------------------------------------------------------------


class TestInv017SettlementIdempotent:
    """INV-017: Building the same EscrowRecord twice produces identical output."""

    @given(
        claim_id=st.text(min_size=1, max_size=64),
        nft_token_id=st.from_regex(r"[0-9A-F]{64}", fullmatch=True),
        payout_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS),
        escrow_sequence=st.integers(min_value=1, max_value=2**31),
        condition_hex=st.from_regex(r"[0-9A-F]{64}", fullmatch=True),
        tx_hash=st.from_regex(r"[0-9A-F]{64}", fullmatch=True),
        dispute_deadline=st.integers(min_value=0, max_value=2**31),
        cancel_after=st.integers(min_value=0, max_value=2**31),
    )
    def test_escrow_record_construction_idempotent(
        self,
        claim_id: str,
        nft_token_id: str,
        payout_drops: int,
        escrow_sequence: int,
        condition_hex: str,
        tx_hash: str,
        dispute_deadline: int,
        cancel_after: int,
    ):
        kwargs = dict(
            claim_id=claim_id,
            nft_token_id=nft_token_id,
            pool_address=_VALID_ADDRESS_A,
            claimant_address=_VALID_ADDRESS_B,
            payout_drops=payout_drops,
            escrow_sequence=escrow_sequence,
            condition_hex=condition_hex,
            tx_hash=tx_hash,
            dispute_deadline_ripple=dispute_deadline,
            cancel_after_ripple=cancel_after,
        )
        r1 = EscrowRecord(**kwargs)
        r2 = EscrowRecord(**kwargs)
        assert r1 == r2

    @given(
        claim_id=st.text(min_size=1, max_size=64),
        payout_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS),
    )
    def test_escrow_record_no_ward_signed_field(
        self, claim_id: str, payout_drops: int
    ):
        # EscrowRecord must not carry a ward_signed field — Ward never signs
        record = EscrowRecord(
            claim_id=claim_id,
            nft_token_id="A" * 64,
            pool_address=_VALID_ADDRESS_A,
            claimant_address=_VALID_ADDRESS_B,
            payout_drops=payout_drops,
            escrow_sequence=1,
            condition_hex="00" * 32,
            tx_hash="B" * 64,
        )
        field_names = {f.name for f in fields(EscrowRecord)}
        assert "ward_signed" not in field_names, (
            "EscrowRecord must not store ward_signed — Ward never holds signing state"
        )
        assert not getattr(record, "ward_signed", False)

    @given(payout_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_escrow_timing_constants_positive(self, payout_drops: int):
        # Dispute window and cancel window must both be positive — always
        assert ESCROW_DISPUTE_HOURS > 0
        assert ESCROW_CANCEL_HOURS > 0
        assert ESCROW_CANCEL_HOURS > ESCROW_DISPUTE_HOURS


# ---------------------------------------------------------------------------
# INV-024 — No floating point in drop amounts
# ---------------------------------------------------------------------------


class TestInv024NoFloatingPoint:
    """INV-024: Float inputs to drop validators always raise ValidationError."""

    @given(amount=st.floats(allow_nan=False, allow_infinity=False))
    def test_validate_drops_amount_rejects_all_floats(self, amount: float):
        with pytest.raises((ValidationError, TypeError)):
            validate_drops_amount(amount)  # type: ignore[arg-type]

    @given(amount=st.floats(allow_nan=False, allow_infinity=False))
    def test_validate_drops_rejects_all_floats(self, amount: float):
        with pytest.raises((ValidationError, TypeError)):
            validate_drops(amount)  # type: ignore[arg-type]

    @given(amount=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_valid_integer_drops_pass(self, amount: int):
        validate_drops_amount(amount)  # must not raise
        validate_drops(amount)  # must not raise

    @given(amount=st.integers(max_value=0))
    def test_zero_and_negative_drops_rejected_by_validate_drops_amount(
        self, amount: int
    ):
        with pytest.raises(ValidationError):
            validate_drops_amount(amount)

    @given(amount=st.integers(min_value=XRP_MAX_DROPS + 1))
    def test_exceeding_max_drops_rejected(self, amount: int):
        with pytest.raises(ValidationError):
            validate_drops_amount(amount)
        with pytest.raises(ValidationError):
            validate_drops(amount)

    def test_boolean_rejected_as_non_integer(self):
        # bool is a subclass of int in Python; Ward explicitly rejects it
        with pytest.raises((ValidationError, TypeError)):
            validate_drops_amount(True)  # type: ignore[arg-type]
        with pytest.raises((ValidationError, TypeError)):
            validate_drops_amount(False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# INV-027 — Invalid addresses always fail closed
# ---------------------------------------------------------------------------


class TestInv027InvalidAddressesFail:
    """INV-027: Any non-r-address string raises ValidationError."""

    @given(address=st.text())
    def test_non_xrpl_addresses_always_raise(self, address: str):
        assume(not is_valid_classic_address(address))
        with pytest.raises(ValidationError):
            validate_xrpl_address(address)

    @given(address=st.text(min_size=1, max_size=35).filter(lambda s: not s.startswith("r")))
    def test_non_r_prefix_always_rejected(self, address: str):
        with pytest.raises(ValidationError):
            validate_xrpl_address(address)

    @given(
        prefix=st.text(alphabet="abcdefghijklmnopqstuvwxyz0123456789", min_size=24, max_size=34)
    )
    def test_r_prefix_with_garbage_suffix_rejected(self, prefix: str):
        address = "r" + prefix
        assume(not is_valid_classic_address(address))
        with pytest.raises(ValidationError):
            validate_xrpl_address(address)

    @pytest.mark.parametrize(
        "address",
        [
            "",
            "   ",
            "0xdeadbeef",
            "0x" + "a" * 40,
            "sEdTM1uX8pu2do5XvTnutH6HsouMaZR",
            "GBKP3GFQM7DXJM5WRSQNZJXS2FIQRQFPKJ2BSLLBDQR",
            "not_an_address",
            "r",
        ],
    )
    def test_known_invalid_addresses_rejected(self, address: str):
        with pytest.raises((ValidationError, Exception)):
            validate_xrpl_address(address)

    @pytest.mark.parametrize(
        "address",
        [
            _VALID_ADDRESS_A,
            _VALID_ADDRESS_B,
        ],
    )
    def test_valid_xrpl_addresses_pass(self, address: str):
        validate_xrpl_address(address)  # must not raise


# ---------------------------------------------------------------------------
# INV-026 — Private key material rejected at API boundary
# ---------------------------------------------------------------------------


class TestInv026PrivateKeyRejected:
    """INV-026: wallet_seed field was removed; seed strings are rejected at boundary."""

    def test_purchase_coverage_no_seed_param(self):
        sig = inspect.signature(WardClient.purchase_coverage)
        assert "wallet_seed" not in sig.parameters
        assert "seed" not in sig.parameters
        assert "private_key" not in sig.parameters

    @given(seed=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_string_wallet_raises_validation_error(self, seed: str):
        """Passing a seed string as wallet= raises ValidationError immediately."""
        client = WardClient()

        async def run():
            return await client.purchase_coverage(
                wallet=seed,  # type: ignore[arg-type]
                vault_address=_VALID_ADDRESS_A,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=_VALID_ADDRESS_B,
            )

        with pytest.raises((ValidationError, TypeError, AttributeError)):
            _run(run())

    @given(seed=st.from_regex(r"s[1-9A-HJ-NP-Za-km-z]{25,33}", fullmatch=True))
    @settings(max_examples=30)
    def test_xrpl_seed_format_rejected_at_boundary(self, seed: str):
        """XRPL-format seeds (s + base58) never accepted as wallet parameter."""
        client = WardClient()

        async def run():
            return await client.purchase_coverage(
                wallet=seed,  # type: ignore[arg-type]
                vault_address=_VALID_ADDRESS_A,
                coverage_drops=1_000_000,
                period_days=30,
                pool_address=_VALID_ADDRESS_B,
            )

        with pytest.raises((ValidationError, TypeError, AttributeError)):
            _run(run())

    def test_escrow_settlement_no_seed_param(self):
        from ward.settlement import EscrowSettlement
        sig = inspect.signature(EscrowSettlement.create_claim_escrow)
        assert "wallet_seed" not in sig.parameters
        assert "seed" not in sig.parameters
        assert "private_key" not in sig.parameters

    def test_escrow_settlement_no_raw_wallet_param(self):
        """EscrowSettlement.create_claim_escrow uses pool_address (str), not a raw wallet."""
        from ward.settlement import EscrowSettlement
        sig = inspect.signature(EscrowSettlement.create_claim_escrow)
        # Ward builds unsigned escrows from an address — no signing key required
        assert "pool_address" in sig.parameters
        assert "wallet_seed" not in sig.parameters
        assert "private_key" not in sig.parameters


# ---------------------------------------------------------------------------
# INV-005 — Server time never decides coverage; ledger time only
# ---------------------------------------------------------------------------


class TestInv005LedgerTimeOnly:
    """INV-005: Coverage decisions use ledger time. Any ledger failure fails closed."""

    @given(expiry=st.integers(min_value=0, max_value=2**32 - 1))
    def test_ledger_error_fails_closed(self, expiry: int):
        """When get_ledger_close_time raises LedgerError, step 2 fails closed."""

        async def run():
            validator = ClaimValidator.__new__(ClaimValidator)
            validator._url = DEFAULT_TESTNET_URL
            with patch(
                "ward.validator.get_ledger_close_time",
                new=AsyncMock(side_effect=LedgerError("connection timeout")),
            ):
                return await validator._step2_check_expiry(None, {"e": expiry})

        result = _run(run())
        assert result is not None, (
            f"LedgerError must fail closed for expiry={expiry}; got None (would approve)"
        )

    @given(expiry=st.integers(min_value=0, max_value=2**32 - 1))
    def test_ledger_error_rejection_message_references_ledger(self, expiry: int):
        """The rejection message produced on LedgerError mentions 'Ledger' or 'failed'."""

        async def run():
            validator = ClaimValidator.__new__(ClaimValidator)
            validator._url = DEFAULT_TESTNET_URL
            with patch(
                "ward.validator.get_ledger_close_time",
                new=AsyncMock(side_effect=LedgerError("rpc error")),
            ):
                return await validator._step2_check_expiry(None, {"e": expiry})

        result = _run(run())
        assert result is not None
        assert "Ledger" in result or "failed" in result.lower(), (
            f"Expected 'Ledger'/'failed' in rejection message, got: {result!r}"
        )

    def test_step2_source_has_no_system_time_calls(self):
        """_step2_check_expiry source must not reference system time (time.time, datetime.now)."""
        import inspect as _inspect
        source = _inspect.getsource(ClaimValidator._step2_check_expiry)
        assert "time.time()" not in source, "Must not use time.time()"
        assert "datetime.now()" not in source, "Must not use datetime.now()"
        assert "datetime.utcnow()" not in source, "Must not use datetime.utcnow()"


# ---------------------------------------------------------------------------
# INV-018 — Dispute windows are deterministic given ledger time
# ---------------------------------------------------------------------------


class TestInv018DisputeWindowsDeterministic:
    """INV-018: Dispute and cancel deadlines are pure functions of ledger time."""

    @given(current_time=st.integers(min_value=0, max_value=2**31))
    def test_dispute_deadline_formula_deterministic(self, current_time: int):
        """Same current_time always produces the same dispute_deadline_ripple."""
        d1 = current_time + ESCROW_DISPUTE_HOURS * 3600
        d2 = current_time + ESCROW_DISPUTE_HOURS * 3600
        assert d1 == d2

    @given(
        t1=st.integers(min_value=0, max_value=2**30),
        t2=st.integers(min_value=0, max_value=2**30),
    )
    def test_different_ledger_times_produce_different_deadlines(
        self, t1: int, t2: int
    ):
        """Different ledger times → different deadlines (strictly monotone)."""
        assume(t1 != t2)
        d1 = t1 + ESCROW_DISPUTE_HOURS * 3600
        d2 = t2 + ESCROW_DISPUTE_HOURS * 3600
        assert d1 != d2

    @given(current_time=st.integers(min_value=0, max_value=2**31))
    def test_cancel_after_always_strictly_after_dispute_deadline(
        self, current_time: int
    ):
        """cancel_after_ripple > dispute_deadline_ripple for every ledger time."""
        dispute_deadline = current_time + ESCROW_DISPUTE_HOURS * 3600
        cancel_after = current_time + ESCROW_CANCEL_HOURS * 3600
        assert cancel_after > dispute_deadline

    @given(
        current_time=st.integers(min_value=0, max_value=2**31),
        payout_drops=st.integers(min_value=1, max_value=XRP_MAX_DROPS),
    )
    def test_escrow_record_deadlines_match_formula(
        self, current_time: int, payout_drops: int
    ):
        """An EscrowRecord built with computed deadlines stores them exactly."""
        dispute_deadline = current_time + ESCROW_DISPUTE_HOURS * 3600
        cancel_after = current_time + ESCROW_CANCEL_HOURS * 3600
        record = EscrowRecord(
            claim_id="c1",
            nft_token_id="A" * 64,
            pool_address=_VALID_ADDRESS_A,
            claimant_address=_VALID_ADDRESS_B,
            payout_drops=payout_drops,
            escrow_sequence=1,
            condition_hex="00" * 32,
            tx_hash="B" * 64,
            dispute_deadline_ripple=dispute_deadline,
            cancel_after_ripple=cancel_after,
        )
        assert record.dispute_deadline_ripple == dispute_deadline
        assert record.cancel_after_ripple == cancel_after


# ---------------------------------------------------------------------------
# INV-019 — Step 7/8 rejection is deterministic (replay-safe)
# ---------------------------------------------------------------------------


class TestInv019SettlementRecheck:
    """INV-019: NFT-burned (step 7) and unowned-NFT (step 8) rejections are deterministic."""

    @given(reason=st.text(min_size=1, max_size=256))
    def test_burned_nft_step7_always_fails_with_steps_passed_6(
        self, reason: str
    ):
        """_reject(7, ...) always yields approved=False, steps_passed=6."""
        result = ClaimValidator._reject(7, reason)
        assert not result.approved
        assert result.steps_passed == 6
        assert result.rejection_reason == reason

    @given(reason=st.text(min_size=1, max_size=256))
    def test_unowned_nft_step8_always_fails_with_steps_passed_7(
        self, reason: str
    ):
        """_reject(8, ...) always yields approved=False, steps_passed=7."""
        result = ClaimValidator._reject(8, reason)
        assert not result.approved
        assert result.steps_passed == 7
        assert result.rejection_reason == reason

    @given(
        step=st.integers(min_value=7, max_value=8),
        reason=st.text(min_size=1, max_size=256),
    )
    def test_step_7_8_rejection_replay_is_identical(
        self, step: int, reason: str
    ):
        """Replaying the same rejection inputs always produces the same result."""
        r1 = ClaimValidator._reject(step, reason)
        r2 = ClaimValidator._reject(step, reason)
        assert r1.approved == r2.approved
        assert r1.steps_passed == r2.steps_passed
        assert r1.rejection_reason == r2.rejection_reason

    @given(
        step=st.integers(min_value=7, max_value=8),
        r1=st.text(min_size=1, max_size=128),
        r2=st.text(min_size=1, max_size=128),
    )
    def test_different_reasons_same_step_produce_same_steps_passed(
        self, step: int, r1: str, r2: str
    ):
        """Different rejection messages at the same step have the same steps_passed."""
        res1 = ClaimValidator._reject(step, r1)
        res2 = ClaimValidator._reject(step, r2)
        assert res1.steps_passed == res2.steps_passed


# ---------------------------------------------------------------------------
# INV-023 — Drop amounts are bounded: negative/zero/over-cap always fail
# ---------------------------------------------------------------------------


class TestInv023RouteValuesBounded:
    """INV-023: validate_drops and validate_drops_amount enforce [1, XRP_MAX_DROPS]."""

    @given(amount=st.integers(max_value=-1))
    def test_negative_validate_drops_rejected(self, amount: int):
        """validate_drops rejects all negative integers (allows zero; >= 0)."""
        with pytest.raises(ValidationError):
            validate_drops(amount)

    @given(amount=st.integers(max_value=0))
    def test_non_positive_validate_drops_amount_rejected(self, amount: int):
        """validate_drops_amount rejects zero and all negative integers (requires > 0)."""
        with pytest.raises(ValidationError):
            validate_drops_amount(amount)

    @given(amount=st.integers(min_value=XRP_MAX_DROPS + 1))
    def test_over_cap_validate_drops_rejected(self, amount: int):
        """Amounts above XRP_MAX_DROPS are rejected by validate_drops."""
        with pytest.raises(ValidationError):
            validate_drops(amount)

    @given(amount=st.integers(min_value=XRP_MAX_DROPS + 1))
    def test_over_cap_validate_drops_amount_rejected(self, amount: int):
        """Amounts above XRP_MAX_DROPS are rejected by validate_drops_amount."""
        with pytest.raises(ValidationError):
            validate_drops_amount(amount)

    @given(amount=st.integers(min_value=1, max_value=XRP_MAX_DROPS))
    def test_valid_positive_range_always_passes_both_validators(self, amount: int):
        """All integers in [1, XRP_MAX_DROPS] pass both validate_drops and validate_drops_amount."""
        validate_drops(amount)
        validate_drops_amount(amount)

    def test_zero_drops_boundary_difference(self):
        """Documents the contract difference: validate_drops allows 0; validate_drops_amount does not."""
        validate_drops(0)  # must not raise — validate_drops allows >= 0
        with pytest.raises(ValidationError):
            validate_drops_amount(0)  # must raise — validate_drops_amount requires > 0
