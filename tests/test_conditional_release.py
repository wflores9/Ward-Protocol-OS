from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ward.resolution import ResolutionDecision, ResolutionError
from ward.workflows.conditional_release import (
    CONDITIONAL_RELEASE_RULES,
    ConditionalReleaseInput,
    resolve_conditional_release,
)

_SIGNER = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
_OWNER = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
_DESTINATION = "rG1QQv2nh2gr7RCZ1P8YYcBUKCCN633jCn"


def _request(**changes) -> ConditionalReleaseInput:
    request = ConditionalReleaseInput(
        case_id="release-case-001",
        asset_or_obligation="escrow:4242",
        institution_signer=_SIGNER,
        escrow_owner=_OWNER,
        destination=_DESTINATION,
        offer_sequence=4242,
        ledger_index=98_765_432,
        ledger_hash="A" * 64,
        event_id="release-event-001",
        event_finalized=True,
        release_condition_met=True,
        participant_eligible=True,
        challenge_window_closed=True,
        observed_at=1_700_000_000,
    )
    return replace(request, **changes)


def test_conditional_release_golden_path_emits_unsigned_action() -> None:
    receipt = resolve_conditional_release(_request())
    data = receipt.to_dict()

    assert receipt.decision is ResolutionDecision.APPROVED
    assert all(check.passed for check in receipt.checks)
    assert data["case"]["workflow_type"] == "conditional_release"
    assert data["case"]["rule_bundle_id"] == CONDITIONAL_RELEASE_RULES.reference
    assert data["unsigned_actions"] == [
        {
            "action_type": "xrpl.escrow_finish",
            "rail": "xrpl",
            "signer": _SIGNER,
            "payload": {
                "TransactionType": "EscrowFinish",
                "Account": _SIGNER,
                "Owner": _OWNER,
                "OfferSequence": 4242,
            },
            "ward_signed": False,
        }
    ]


def test_conditional_release_replays_to_identical_receipt() -> None:
    first = resolve_conditional_release(_request())
    second = resolve_conditional_release(_request())

    assert first.receipt_hash == second.receipt_hash
    assert first.canonical_json() == second.canonical_json()


@pytest.mark.parametrize(
    "field",
    [
        "event_finalized",
        "release_condition_met",
        "participant_eligible",
        "challenge_window_closed",
    ],
)
def test_conditional_release_fails_closed_when_condition_is_false(field: str) -> None:
    receipt = resolve_conditional_release(_request(**{field: False}))

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()
    assert any(not check.passed for check in receipt.checks)


def test_conditional_release_receipt_carries_replay_provenance() -> None:
    receipt = resolve_conditional_release(_request())
    evidence = receipt.evidence[0].to_dict()

    assert evidence["source_type"] == "ledger_event"
    assert evidence["finality"] == "validated"
    assert "98765432" in evidence["locator"]
    assert ("a" * 64) in evidence["locator"]
    assert evidence["content_hash"] == receipt.evidence[0].content_hash
    assert len(evidence["content_hash"]) == 64


def test_conditional_release_is_not_insurance_or_xls66_shaped() -> None:
    serialized = json.dumps(resolve_conditional_release(_request()).to_dict()).lower()

    for excluded_term in (
        "xls-66",
        "insurance",
        "coverage",
        "premium",
        "policy nft",
        "loss pool",
    ):
        assert excluded_term not in serialized


def test_conditional_release_preserves_external_signer_boundary() -> None:
    receipt = resolve_conditional_release(_request())
    action = receipt.unsigned_actions[0]

    assert receipt.case.signer == _SIGNER
    assert action.signer == _SIGNER
    assert action.ward_signed is False
    assert "TxnSignature" not in action.payload
    assert "SigningPubKey" not in action.payload


def test_conditional_release_rejects_an_unsupported_rail() -> None:
    with pytest.raises(ResolutionError, match="currently supports the XRPL rail"):
        _request(rail="stellar")
