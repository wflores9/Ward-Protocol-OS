"""Golden non-XLS-66 workflow: deterministic conditional release."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ward.resolution import (
    EvidenceReceipt,
    EvidenceReference,
    ResolutionCase,
    ResolutionEngine,
    ResolutionError,
    Rule,
    RuleBundle,
    RuleOperator,
    UnsignedAction,
    canonical_hash,
)

_HEX_64_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_SOURCE_ID = "ledger_event"

CONDITIONAL_RELEASE_RULES = RuleBundle(
    bundle_id="ward.conditional-release",
    version="1.0.0",
    rules=(
        Rule(
            rule_id="CR-01",
            field="event.finalized",
            operator=RuleOperator.EQ,
            expected=True,
            evidence_refs=(_SOURCE_ID,),
        ),
        Rule(
            rule_id="CR-02",
            field="release.condition_met",
            operator=RuleOperator.EQ,
            expected=True,
            evidence_refs=(_SOURCE_ID,),
        ),
        Rule(
            rule_id="CR-03",
            field="participant.eligible",
            operator=RuleOperator.EQ,
            expected=True,
            evidence_refs=(_SOURCE_ID,),
        ),
        Rule(
            rule_id="CR-04",
            field="challenge.window_closed",
            operator=RuleOperator.EQ,
            expected=True,
            evidence_refs=(_SOURCE_ID,),
        ),
        Rule(
            rule_id="CR-05",
            field="escrow.offer_sequence",
            operator=RuleOperator.GT,
            expected=0,
            evidence_refs=(_SOURCE_ID,),
        ),
    ),
)


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResolutionError(f"{label} must be a non-empty string")


@dataclass(frozen=True)
class ConditionalReleaseInput:
    case_id: str
    asset_or_obligation: str
    institution_signer: str
    escrow_owner: str
    destination: str
    offer_sequence: int
    ledger_index: int
    ledger_hash: str
    event_id: str
    event_finalized: bool
    release_condition_met: bool
    participant_eligible: bool
    challenge_window_closed: bool
    observed_at: int
    rail: str = "xrpl"

    def __post_init__(self) -> None:
        for label in (
            "case_id",
            "asset_or_obligation",
            "institution_signer",
            "escrow_owner",
            "destination",
            "event_id",
            "rail",
        ):
            _text(getattr(self, label), label)
        if self.rail != "xrpl":
            raise ResolutionError(
                "conditional release currently supports the XRPL rail"
            )
        if (
            isinstance(self.offer_sequence, bool)
            or not isinstance(self.offer_sequence, int)
            or self.offer_sequence <= 0
        ):
            raise ResolutionError("offer_sequence must be a positive integer")
        if (
            isinstance(self.ledger_index, bool)
            or not isinstance(self.ledger_index, int)
            or self.ledger_index <= 0
        ):
            raise ResolutionError("ledger_index must be a positive integer")
        if not isinstance(self.observed_at, int) or isinstance(self.observed_at, bool):
            raise ResolutionError("observed_at must be a non-negative integer")
        if self.observed_at < 0:
            raise ResolutionError("observed_at must be a non-negative integer")
        if not isinstance(self.ledger_hash, str) or not _HEX_64_RE.fullmatch(
            self.ledger_hash
        ):
            raise ResolutionError("ledger_hash must be a 64-character hex digest")
        for label in (
            "event_finalized",
            "release_condition_met",
            "participant_eligible",
            "challenge_window_closed",
        ):
            if not isinstance(getattr(self, label), bool):
                raise ResolutionError(f"{label} must be boolean")


def resolve_conditional_release(
    request: ConditionalReleaseInput,
) -> EvidenceReceipt:
    """Resolve one conditional-release event without signing or submitting it."""

    facts = {
        "event": {
            "id": request.event_id,
            "finalized": request.event_finalized,
        },
        "release": {"condition_met": request.release_condition_met},
        "participant": {"eligible": request.participant_eligible},
        "challenge": {"window_closed": request.challenge_window_closed},
        "escrow": {"offer_sequence": request.offer_sequence},
    }
    evidence = EvidenceReference(
        source_id=_SOURCE_ID,
        source_type="ledger_event",
        locator=(
            f"{request.rail}:ledger/{request.ledger_index}/"
            f"{request.ledger_hash.lower()}"
        ),
        observed_at=request.observed_at,
        finality="validated" if request.event_finalized else "unvalidated",
        content_hash=canonical_hash(facts),
        claims=facts,
    )
    case = ResolutionCase(
        case_id=request.case_id,
        workflow_type="conditional_release",
        rail=request.rail,
        asset_or_obligation=request.asset_or_obligation,
        trigger="release_condition_observed",
        source_of_truth=evidence.locator,
        rule_bundle_id=CONDITIONAL_RELEASE_RULES.reference,
        signer=request.institution_signer,
        requested_action="xrpl.escrow_finish",
        metadata={
            "event_id": request.event_id,
            "ledger_index": request.ledger_index,
            "ledger_hash": request.ledger_hash.lower(),
            "beneficiary": request.destination,
        },
    )
    action = UnsignedAction(
        action_type="xrpl.escrow_finish",
        rail=request.rail,
        signer=request.institution_signer,
        payload={
            "TransactionType": "EscrowFinish",
            "Account": request.institution_signer,
            "Owner": request.escrow_owner,
            "OfferSequence": request.offer_sequence,
        },
    )
    return ResolutionEngine().evaluate(
        case=case,
        facts=facts,
        rule_bundle=CONDITIONAL_RELEASE_RULES,
        evidence=(evidence,),
        proposed_actions=(action,),
        observed_at=request.observed_at,
        assumptions=(
            "The supplied ledger event is independently retrievable by its locator.",
            "The institution reviews and signs any resulting action.",
        ),
    )
