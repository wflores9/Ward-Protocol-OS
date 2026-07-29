"""Netten Circles tax-reserve release workflow."""

from __future__ import annotations

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

_SOURCE_ID = "tax_reserve_circle_state"

NETTEN_TAX_RESERVE_CIRCLE_RULES = RuleBundle(
    bundle_id="ward.netten-circles-tax-reserve",
    version="1.0.0",
    rules=(
        Rule("NC-01", "job.completed", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NC-02", "reserve.created", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NC-03", "reserve.amount_matches_policy", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NC-04", "review.window_closed", RuleOperator.EQ, True, (_SOURCE_ID,)),
        Rule("NC-05", "client.disapproved_assets", RuleOperator.EQ, False, (_SOURCE_ID,)),
        Rule("NC-06", "signer.external", RuleOperator.EQ, True, (_SOURCE_ID,)),
    ),
)


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResolutionError(f"{label} must be a non-empty string")


def _positive_number(value: float | int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ResolutionError(f"{label} must be a positive number")


def _bool(value: bool, label: str) -> None:
    if not isinstance(value, bool):
        raise ResolutionError(f"{label} must be boolean")


@dataclass(frozen=True)
class NettenTaxReserveCircleInput:
    case_id: str
    circle_id: str
    event_id: str
    job_amount: float
    reserve_percentage: float
    reserve_amount: float
    review_window_hours: int
    review_window_closed: bool
    client_disapproved_assets: bool
    freelancer_or_agency: str
    client: str
    release_authority: str
    observed_at: int
    rail: str = "xrpl"

    def __post_init__(self) -> None:
        for label in (
            "case_id",
            "circle_id",
            "event_id",
            "freelancer_or_agency",
            "client",
            "release_authority",
            "rail",
        ):
            _text(getattr(self, label), label)
        if self.rail != "xrpl":
            raise ResolutionError("Netten Circles tax reserve currently supports the XRPL rail")
        for label in ("job_amount", "reserve_percentage", "reserve_amount"):
            _positive_number(getattr(self, label), label)
        if self.reserve_percentage > 100:
            raise ResolutionError("reserve_percentage must be less than or equal to 100")
        if isinstance(self.review_window_hours, bool) or not isinstance(self.review_window_hours, int) or self.review_window_hours <= 0:
            raise ResolutionError("review_window_hours must be a positive integer")
        if isinstance(self.observed_at, bool) or not isinstance(self.observed_at, int) or self.observed_at < 0:
            raise ResolutionError("observed_at must be a non-negative integer")
        _bool(self.review_window_closed, "review_window_closed")
        _bool(self.client_disapproved_assets, "client_disapproved_assets")


def _amount_matches_policy(request: NettenTaxReserveCircleInput) -> bool:
    expected = request.job_amount * (request.reserve_percentage / 100)
    return round(expected, 8) == round(request.reserve_amount, 8)


def resolve_netten_tax_reserve_circle(request: NettenTaxReserveCircleInput) -> EvidenceReceipt:
    amount_matches_policy = _amount_matches_policy(request)
    reserve_created = request.reserve_amount > 0 and amount_matches_policy

    facts = {
        "job": {"completed": True, "amount": request.job_amount},
        "reserve": {
            "created": reserve_created,
            "percentage": request.reserve_percentage,
            "amount": request.reserve_amount,
            "amount_matches_policy": amount_matches_policy,
        },
        "review": {
            "window_hours": request.review_window_hours,
            "window_closed": request.review_window_closed,
        },
        "client": {
            "disapproved_assets": request.client_disapproved_assets,
            "account": request.client,
        },
        "signer": {"external": True, "authority": request.release_authority},
        "circle": {
            "id": request.circle_id,
            "freelancer_or_agency": request.freelancer_or_agency,
        },
    }

    evidence = EvidenceReference(
        source_id=_SOURCE_ID,
        source_type="tax_reserve_circle_state",
        locator=f"{request.rail}:netten-circle/{request.circle_id}/{request.event_id}",
        observed_at=request.observed_at,
        finality="verified" if reserve_created else "incomplete",
        content_hash=canonical_hash(facts),
        claims=facts,
    )

    case = ResolutionCase(
        case_id=request.case_id,
        workflow_type="netten_tax_reserve_circle",
        rail=request.rail,
        asset_or_obligation=f"tax-reserve-circle:{request.circle_id}",
        trigger="tax_reserve_release_review",
        source_of_truth=evidence.locator,
        rule_bundle_id=NETTEN_TAX_RESERVE_CIRCLE_RULES.reference,
        signer=request.release_authority,
        requested_action="netten.circle_release_review",
        metadata={
            "circle_id": request.circle_id,
            "event_id": request.event_id,
            "job_amount": request.job_amount,
            "reserve_percentage": request.reserve_percentage,
            "reserve_amount": request.reserve_amount,
            "review_window_hours": request.review_window_hours,
            "client": request.client,
            "freelancer_or_agency": request.freelancer_or_agency,
            "client_disapproved_assets": request.client_disapproved_assets,
        },
    )

    action = UnsignedAction(
        action_type="netten.circle_release_review",
        rail=request.rail,
        signer=request.release_authority,
        payload={
            "Action": "CircleReserveReleaseReview",
            "CircleID": request.circle_id,
            "ReserveAmount": request.reserve_amount,
            "ReleaseAuthority": request.release_authority,
            "Client": request.client,
            "FreelancerOrAgency": request.freelancer_or_agency,
        },
    )

    return ResolutionEngine().evaluate(
        case=case,
        facts=facts,
        rule_bundle=NETTEN_TAX_RESERVE_CIRCLE_RULES,
        evidence=(evidence,),
        proposed_actions=(action,),
        observed_at=request.observed_at,
        assumptions=(
            "Ward evaluates supplied Netten Circles tax-reserve facts against fixed release-review rules; it does not custody reserves.",
            "The freelancer, agency, client, or Netten release authority reviews and executes any release externally.",
            "Client disapproval or an open review window blocks the automated release-review path for party-handled resolution.",
        ),
    )
