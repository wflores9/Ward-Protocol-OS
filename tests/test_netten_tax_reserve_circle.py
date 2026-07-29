from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ward.resolution import ResolutionDecision, ResolutionError
from ward.workflows.netten_tax_reserve_circle import (
    NETTEN_TAX_RESERVE_CIRCLE_RULES,
    NettenTaxReserveCircleInput,
    resolve_netten_tax_reserve_circle,
)


def _request(**changes) -> NettenTaxReserveCircleInput:
    request = NettenTaxReserveCircleInput(
        case_id="netten-tax-reserve-circle-001",
        circle_id="circle-tax-reserve-001",
        event_id="circle-job-completed-001",
        job_amount=1500,
        reserve_percentage=50,
        reserve_amount=750,
        review_window_hours=72,
        review_window_closed=True,
        client_disapproved_assets=False,
        freelancer_or_agency="freelancer-alpha",
        client="client-beta",
        release_authority="freelancer/agency + client",
        observed_at=1_700_000_300,
    )
    return replace(request, **changes)


def test_netten_tax_reserve_circle_golden_path_emits_unsigned_release_review() -> None:
    receipt = resolve_netten_tax_reserve_circle(_request())
    data = receipt.to_dict()

    assert receipt.decision is ResolutionDecision.APPROVED
    assert data["case"]["workflow_type"] == "netten_tax_reserve_circle"
    assert data["case"]["rule_bundle_id"] == NETTEN_TAX_RESERVE_CIRCLE_RULES.reference
    assert data["case"]["metadata"]["reserve_amount"] == 750
    assert data["unsigned_actions"][0]["ward_signed"] is False
    assert data["unsigned_actions"][0]["payload"] == {
        "Action": "CircleReserveReleaseReview",
        "CircleID": "circle-tax-reserve-001",
        "ReserveAmount": 750,
        "ReleaseAuthority": "freelancer/agency + client",
        "Client": "client-beta",
        "FreelancerOrAgency": "freelancer-alpha",
    }


def test_netten_tax_reserve_circle_replays_to_identical_receipt() -> None:
    first = resolve_netten_tax_reserve_circle(_request())
    second = resolve_netten_tax_reserve_circle(_request())

    assert first.receipt_hash == second.receipt_hash
    assert first.canonical_json() == second.canonical_json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_window_closed", False),
        ("client_disapproved_assets", True),
        ("reserve_amount", 700),
    ],
)
def test_failed_tax_reserve_conditions_reject_without_action(field: str, value: object) -> None:
    receipt = resolve_netten_tax_reserve_circle(_request(**{field: value}))

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()


def test_netten_tax_reserve_circle_is_not_xls66_or_insurance_shaped() -> None:
    serialized = json.dumps(resolve_netten_tax_reserve_circle(_request()).to_dict()).lower()

    for excluded_term in ("xls-66", "insurance", "coverage", "premium", "policy nft", "loss pool"):
        assert excluded_term not in serialized


def test_netten_tax_reserve_circle_preserves_signer_boundary() -> None:
    receipt = resolve_netten_tax_reserve_circle(_request())
    action = receipt.unsigned_actions[0]

    assert receipt.ward_signed is False
    assert action.ward_signed is False
    assert action.signer == "freelancer/agency + client"
    assert "TxnSignature" not in action.payload
    assert "SigningPubKey" not in action.payload


def test_netten_tax_reserve_circle_rejects_unsupported_rail() -> None:
    with pytest.raises(ResolutionError, match="currently supports the XRPL rail"):
        _request(rail="xahau")