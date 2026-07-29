from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from ward.resolution import (
    EvidenceReference,
    ResolutionCase,
    ResolutionDecision,
    ResolutionEngine,
    ResolutionError,
    Rule,
    RuleBundle,
    RuleOperator,
    UnsignedAction,
    canonical_hash,
    canonical_json,
)


def _bundle() -> RuleBundle:
    return RuleBundle(
        bundle_id="ward.test-release",
        version="1.0.0",
        rules=(
            Rule(
                rule_id="TR-01",
                field="event.finalized",
                operator=RuleOperator.EQ,
                expected=True,
                evidence_refs=("event_record",),
            ),
            Rule(
                rule_id="TR-02",
                field="amount",
                operator=RuleOperator.GT,
                expected=0,
                evidence_refs=("event_record",),
            ),
        ),
    )


def _case(bundle: RuleBundle) -> ResolutionCase:
    return ResolutionCase(
        case_id="case-001",
        workflow_type="test_release",
        rail="test_rail",
        asset_or_obligation="asset-001",
        trigger="event_observed",
        source_of_truth="test-ledger:100",
        rule_bundle_id=bundle.reference,
        signer="institution:treasury",
        requested_action="test.release",
        metadata={"b": 2, "a": 1},
    )


def _evidence(facts: dict) -> EvidenceReference:
    return EvidenceReference(
        source_id="event_record",
        source_type="ledger_event",
        locator="test-ledger:100/ABC",
        observed_at=1_700_000_000,
        finality="final",
        content_hash=canonical_hash(facts),
        claims=facts,
    )


def _action(
    signer: str = "institution:treasury", rail: str = "test_rail"
) -> UnsignedAction:
    return UnsignedAction(
        action_type="test.release",
        rail=rail,
        signer=signer,
        payload={"Amount": 25, "Destination": "beneficiary:001"},
    )


def _resolve(facts: dict):
    bundle = _bundle()
    return ResolutionEngine().evaluate(
        case=_case(bundle),
        facts=facts,
        rule_bundle=bundle,
        evidence=(_evidence(facts),),
        proposed_actions=(_action(),),
        observed_at=1_700_000_000,
    )


def test_canonical_hash_is_independent_of_mapping_insertion_order() -> None:
    left = {"event": {"finalized": True, "id": "evt-1"}, "amount": 25}
    right = {"amount": 25, "event": {"id": "evt-1", "finalized": True}}

    assert canonical_json(left) == canonical_json(right)
    assert canonical_hash(left) == canonical_hash(right)


def test_approved_receipt_is_replayable_and_unsigned() -> None:
    receipt = _resolve({"event": {"finalized": True}, "amount": 25})
    data = receipt.to_dict()

    assert receipt.decision is ResolutionDecision.APPROVED
    assert receipt.receipt_id.startswith("wr_")
    assert len(receipt.receipt_hash) == 64
    assert data["unsigned_actions"][0]["ward_signed"] is False
    assert "TxnSignature" not in data["unsigned_actions"][0]["payload"]
    assert hashlib.sha256(receipt.canonical_json().encode()).hexdigest() == (
        receipt.receipt_hash
    )
    assert json.loads(receipt.canonical_json())["decision"] == "approved"



def test_serialized_receipt_hash_replays_without_derived_fields() -> None:
    receipt = _resolve({"event": {"finalized": True}, "amount": 25}).to_dict()

    stored_hash = receipt["receipt_hash"]
    payload = dict(receipt)
    payload.pop("receipt_id")
    payload.pop("receipt_hash")

    assert canonical_hash(payload) == stored_hash


def test_same_inputs_replay_to_same_receipt_hash() -> None:
    first = _resolve({"event": {"finalized": True}, "amount": 25})
    second = _resolve({"amount": 25, "event": {"finalized": True}})

    assert first.receipt_hash == second.receipt_hash
    assert first.receipt_id == second.receipt_id


def test_changed_fact_changes_receipt_hash() -> None:
    first = _resolve({"event": {"finalized": True}, "amount": 25})
    second = _resolve({"event": {"finalized": True}, "amount": 26})

    assert first.receipt_hash != second.receipt_hash


def test_missing_fact_fails_closed_and_strips_actions() -> None:
    receipt = _resolve({"event": {"finalized": True}})

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()
    assert receipt.checks[1].passed is False
    assert "failed closed" in receipt.checks[1].detail


def test_missing_evidence_reference_rejects_without_action() -> None:
    bundle = RuleBundle(
        bundle_id="ward.missing-evidence",
        version="1.0.0",
        rules=(
            Rule(
                rule_id="ME-01",
                field="ready",
                operator=RuleOperator.EQ,
                expected=True,
                evidence_refs=("other_source",),
            ),
        ),
    )
    facts = {"ready": True}
    case = ResolutionCase(
        case_id="case-missing-evidence",
        workflow_type="release",
        rail="test_rail",
        asset_or_obligation="asset-001",
        trigger="ready",
        source_of_truth="test-ledger:100",
        rule_bundle_id=bundle.reference,
        signer="institution:treasury",
        requested_action="test.release",
    )
    receipt = ResolutionEngine().evaluate(
        case=case,
        facts=facts,
        rule_bundle=bundle,
        evidence=(_evidence(facts),),
        proposed_actions=(_action(),),
        observed_at=1_700_000_000,
    )

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()
    assert receipt.checks[0].detail == "missing evidence: other_source"


def test_fact_must_match_the_claim_in_its_authoritative_evidence() -> None:
    facts = {"event": {"finalized": True}, "amount": 25}
    conflicting_claims = {"event": {"finalized": True}, "amount": 0}
    bundle = _bundle()

    receipt = ResolutionEngine().evaluate(
        case=_case(bundle),
        facts=facts,
        rule_bundle=bundle,
        evidence=(_evidence(conflicting_claims),),
        proposed_actions=(_action(),),
        observed_at=1_700_000_000,
    )

    assert receipt.decision is ResolutionDecision.REJECTED
    assert receipt.unsigned_actions == ()
    assert receipt.checks[1].detail == "evidence claim mismatch: event_record"


def test_receipt_invariants_cannot_be_bypassed_by_direct_construction() -> None:
    receipt = _resolve({"event": {"finalized": True}, "amount": 25})

    with pytest.raises(ResolutionError, match="decision"):
        replace(receipt, decision=ResolutionDecision.REJECTED, unsigned_actions=())

    failed_checks = tuple(replace(check, passed=False) for check in receipt.checks)
    with pytest.raises(ResolutionError, match="rejected receipts"):
        replace(
            receipt,
            decision=ResolutionDecision.REJECTED,
            checks=failed_checks,
            unsigned_actions=receipt.unsigned_actions,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"TxnSignature": "DEADBEEF"},
        {"SigningPubKey": "02ABC"},
        {"Signers": [{"Signer": {"TxnSignature": "DEADBEEF"}}]},
        {"private_key": "do-not-store"},
        {"nested": {"seed": "do-not-store"}},
    ],
)
def test_unsigned_action_rejects_signatures_and_key_material(payload: dict) -> None:
    with pytest.raises(ResolutionError):
        UnsignedAction(
            action_type="test.release",
            rail="test_rail",
            signer="institution:treasury",
            payload=payload,
        )


def test_action_must_preserve_case_signer_and_rail() -> None:
    facts = {"event": {"finalized": True}, "amount": 25}
    bundle = _bundle()

    with pytest.raises(ResolutionError, match="signer"):
        ResolutionEngine().evaluate(
            case=_case(bundle),
            facts=facts,
            rule_bundle=bundle,
            evidence=(_evidence(facts),),
            proposed_actions=(_action(signer="other:signer"),),
            observed_at=1_700_000_000,
        )

    with pytest.raises(ResolutionError, match="rail"):
        ResolutionEngine().evaluate(
            case=_case(bundle),
            facts=facts,
            rule_bundle=bundle,
            evidence=(_evidence(facts),),
            proposed_actions=(_action(rail="other_rail"),),
            observed_at=1_700_000_000,
        )

    wrong_type = UnsignedAction(
        action_type="test.other",
        rail="test_rail",
        signer="institution:treasury",
        payload={"Amount": 25},
    )
    with pytest.raises(ResolutionError, match="action type"):
        ResolutionEngine().evaluate(
            case=_case(bundle),
            facts=facts,
            rule_bundle=bundle,
            evidence=(_evidence(facts),),
            proposed_actions=(wrong_type,),
            observed_at=1_700_000_000,
        )


def test_case_must_reference_exact_rule_bundle_version() -> None:
    bundle = _bundle()
    case = ResolutionCase(
        case_id="case-001",
        workflow_type="test_release",
        rail="test_rail",
        asset_or_obligation="asset-001",
        trigger="event_observed",
        source_of_truth="test-ledger:100",
        rule_bundle_id="ward.test-release@0.9.0",
        signer="institution:treasury",
        requested_action="test.release",
    )
    facts = {"event": {"finalized": True}, "amount": 25}

    with pytest.raises(ResolutionError, match="rule_bundle_id"):
        ResolutionEngine().evaluate(
            case=case,
            facts=facts,
            rule_bundle=bundle,
            evidence=(_evidence(facts),),
            proposed_actions=(_action(),),
            observed_at=1_700_000_000,
        )
