from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ward.resolution import ResolutionDecision, ResolutionError
from ward.workflows.netten_escrow_release import (
    NETTEN_ESCROW_RELEASE_RULES,
    NettenEscrowReleaseInput,
    resolve_netten_escrow_release,
)

_SIGNER = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
_OWNER = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"

def _request(**changes) -> NettenEscrowReleaseInput:
    request = NettenEscrowReleaseInput(
        case_id="netten-escrow-001",
        asset_or_obligation="services-deposit:design-project-001",
        institution_signer=_SIGNER,
        escrow_owner=_OWNER,
        service_provider="designer-alpha",
        client="client-beta",
        offer_sequence=7251,
        ledger_index=100200300,
        ledger_hash="B" * 64,
        event_id="netten-services-release-001",
        deposit_received=True,
        service_rendered=True,
        client_accepted=True,
        release_interval_elapsed=False,
        dispute_open=False,
        egregious_dispute=False,
        observed_at=1_700_000_100,
    )
    return replace(request, **changes)

def test_netten_escrow_release_golden_path_emits_unsigned_action() -> None:
    receipt = resolve_netten_escrow_release(_request())
    data = receipt.to_dict()

    assert receipt.decision is ResolutionDecision.APPROVED
    assert data["case"]["workflow_type"] == "netten_escrow_release"
    assert data["case"]["rule_bundle_id"] == NETTEN_ESCROW_RELEASE_RULES.reference
    assert data["case"]["metadata"]["release_basis"] == "client_acceptance"
    assert data["unsigned_actions"][0]["ward_signed"] is False
    assert data["unsigned_actions"][0]["payload"] == {
        "TransactionType": "EscrowFinish",
        "Account": _SIGNER,
        "Owner": _OWNER,
        "OfferSequence": 7251,
    }

def test_netten_escrow_release_replays_to_identical_receipt() -> None:
    first = resolve_netten_escrow_release(_request())
    second = resolve_netten_escrow_release(_request())

    assert first.receipt_hash == second.receipt_hash
    assert first.canonical_json() == second.canonical_json()

def test_release_interval_can_authorize_without_client_acceptance() -> None:
    receipt = resolve_netten_escrow_release(
        _request(client_accepted=False, release_interval_elapsed=True)
    )

    assert receipt.decision is ResolutionDecision.APPROVED
    assert receipt.case.metadata["release_basis"] == "release_interval"

def test_non_egregious_dispute_does_not_make_ward_the_judge() -> None:
    receipt = resolve_netten_escrow_release(_request(dispute_open=True))

    assert receipt.decision is ResolutionDecision.APPROVED
    assert any("does not judge work quality" in item for item in receipt.assumptions)

@pytest.mark.parametrize("field", ["deposit_received", "service_rendered"])
def test_required_false_fact_rejects_without_action(field: str) -> None:
    receipt = resolve_netten_escrow_release(_request(**{field: False}))

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()

def test_release_without_acceptance_or_interval_rejects_without_action() -> None:
    receipt = resolve_netten_escrow_release(
        _request(client_accepted=False, release_interval_elapsed=False)
    )

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()

def test_egregious_dispute_blocks_release_for_external_handling() -> None:
    receipt = resolve_netten_escrow_release(
        _request(dispute_open=True, egregious_dispute=True)
    )

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()

def test_netten_adapter_is_not_xls66_or_insurance_shaped() -> None:
    serialized = json.dumps(resolve_netten_escrow_release(_request()).to_dict()).lower()

    for excluded_term in ("xls-66", "insurance", "coverage", "premium", "policy nft", "loss pool"):
        assert excluded_term not in serialized

def test_netten_adapter_preserves_signer_boundary() -> None:
    receipt = resolve_netten_escrow_release(_request())
    action = receipt.unsigned_actions[0]

    assert receipt.ward_signed is False
    assert action.ward_signed is False
    assert action.signer == _SIGNER
    assert "TxnSignature" not in action.payload
    assert "SigningPubKey" not in action.payload

def test_netten_adapter_rejects_unsupported_rail() -> None:
    with pytest.raises(ResolutionError, match="currently supports the XRPL rail"):
        _request(rail="xahau")
