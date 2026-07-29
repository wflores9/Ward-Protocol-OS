from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ward.workflows import ConditionalReleaseInput, resolve_conditional_release

_SCHEMA = json.loads(
    Path("schemas/ward-resolution-receipt-v1.schema.json").read_text(encoding="utf-8")
)
_VALIDATOR = Draft202012Validator(_SCHEMA)


def _receipt(*, challenge_window_closed: bool = True) -> dict:
    return resolve_conditional_release(
        ConditionalReleaseInput(
            case_id="schema-case-001",
            asset_or_obligation="escrow:42",
            institution_signer="rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
            escrow_owner="rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
            destination="rG1QQv2nh2gr7RCZ1P8YYcBUKCCN633jCn",
            offer_sequence=42,
            ledger_index=98_765_432,
            ledger_hash="D" * 64,
            event_id="schema-event-001",
            event_finalized=True,
            release_condition_met=True,
            participant_eligible=True,
            challenge_window_closed=challenge_window_closed,
            observed_at=1_700_000_000,
        )
    ).to_dict()


def test_receipt_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_SCHEMA)


def test_approved_receipt_matches_public_schema() -> None:
    _VALIDATOR.validate(_receipt())


def test_rejected_receipt_matches_public_schema_without_actions() -> None:
    receipt = _receipt(challenge_window_closed=False)

    assert receipt["unsigned_actions"] == []
    _VALIDATOR.validate(receipt)


def test_schema_rejects_claim_that_ward_signed() -> None:
    receipt = _receipt()
    receipt["ward_signed"] = True

    with pytest.raises(ValidationError):
        _VALIDATOR.validate(receipt)


def test_schema_rejects_action_on_rejected_receipt() -> None:
    approved = _receipt()
    rejected = _receipt(challenge_window_closed=False)
    rejected["unsigned_actions"] = deepcopy(approved["unsigned_actions"])

    with pytest.raises(ValidationError):
        _VALIDATOR.validate(rejected)
