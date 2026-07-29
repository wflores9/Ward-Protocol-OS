"""Netten-style services escrow release workflow."""

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
_SOURCE_ID = "escrow_workflow_state"

NETTEN_ESCROW_RELEASE_RULES = RuleBundle(
    bundle_id="ward.netten-escrow-release",
    version="1.0.0",
    rules=(
        Rule("NE-01", "deposit.received", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NE-02", "service.rendered", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NE-03", "release.authorized", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NE-04", "dispute.egregious", RuleOperator.EQ, False, (_SOURCE_ID,)),
        Rule("NE-05", "signer.external", RuleOperator.EQ, True, (_SOURCE_ID,)),
    ),
)


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResolutionError(f"{label} must be a non-empty string")


@dataclass(frozen=True)
class NettenEscrowReleaseInput:
    case_id: str
    asset_or_obligation: str
    institution_signer: str
    escrow_owner: str
    service_provider: str
    client: str
    offer_sequence: int
    ledger_index: int
    ledger_hash: str
    event_id: str
    deposit_received: bool
    service_rendered: bool
    client_accepted: bool
    release_interval_elapsed: bool
    dispute_open: bool
    egregious_dispute: bool
    observed_at: int
    rail: str = "xrpl"

    def __post_init__(self) -> None:
        for label in (
            "case_id",
            "asset_or_obligation",
            "institution_signer",
            "escrow_owner",
            "service_provider",
            "client",
            "event_id",
            "rail",
        ):
            _text(getattr(self, label), label)
        if self.rail != "xrpl":
            raise ResolutionError(
                "Netten escrow release currently supports the XRPL rail"
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
        if (
            not isinstance(self.observed_at, int)
            or isinstance(self.observed_at, bool)
            or self.observed_at < 0
        ):
            raise ResolutionError("observed_at must be a non-negative integer")
        if not isinstance(self.ledger_hash, str) or not _HEX_64_RE.fullmatch(
            self.ledger_hash
        ):
            raise ResolutionError("ledger_hash must be a 64-character hex digest")
        for label in (
            "deposit_received",
            "service_rendered",
            "client_accepted",
            "release_interval_elapsed",
            "dispute_open",
            "egregious_dispute",
        ):
            if not isinstance(getattr(self, label), bool):
                raise ResolutionError(f"{label} must be boolean")


def resolve_netten_escrow_release(request: NettenEscrowReleaseInput) -> EvidenceReceipt:
    release_authorized = request.client_accepted or request.release_interval_elapsed
    release_basis = (
        "client_acceptance"
        if request.client_accepted
        else "release_interval"
        if request.release_interval_elapsed
        else "none"
    )

    facts = {
        "deposit": {"received": request.deposit_received},
        "service": {"rendered": request.service_rendered},
        "release": {
            "authorized": release_authorized,
            "client_accepted": request.client_accepted,
            "interval_elapsed": request.release_interval_elapsed,
            "basis": release_basis,
        },
        "dispute": {
            "open": request.dispute_open,
            "egregious": request.egregious_dispute,
        },
        "signer": {"external": True, "account": request.institution_signer},
        "escrow": {
            "owner": request.escrow_owner,
            "offer_sequence": request.offer_sequence,
            "service_provider": request.service_provider,
            "client": request.client,
        },
    }

    evidence = EvidenceReference(
        source_id=_SOURCE_ID,
        source_type="escrow_workflow_state",
        locator=f"{request.rail}:ledger/{request.ledger_index}/{request.ledger_hash.lower()}/{request.event_id}",
        observed_at=request.observed_at,
        finality="validated" if request.deposit_received else "unvalidated",
        content_hash=canonical_hash(facts),
        claims=facts,
    )

    case = ResolutionCase(
        case_id=request.case_id,
        workflow_type="netten_escrow_release",
        rail=request.rail,
        asset_or_obligation=request.asset_or_obligation,
        trigger="services_escrow_release_review",
        source_of_truth=evidence.locator,
        rule_bundle_id=NETTEN_ESCROW_RELEASE_RULES.reference,
        signer=request.institution_signer,
        requested_action="xrpl.escrow_finish",
        metadata={
            "event_id": request.event_id,
            "ledger_index": request.ledger_index,
            "ledger_hash": request.ledger_hash.lower(),
            "client": request.client,
            "service_provider": request.service_provider,
            "dispute_open": request.dispute_open,
            "release_basis": release_basis,
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
        rule_bundle=NETTEN_ESCROW_RELEASE_RULES,
        evidence=(evidence,),
        proposed_actions=(action,),
        observed_at=request.observed_at,
        assumptions=(
            "Ward evaluates supplied service-escrow facts against fixed release rules; it does not judge work quality.",
            "The institution or escrow authority reviews and signs any resulting action externally.",
            "Egregious disputes block the automated release path for party-handled escalation.",
        ),
    )
