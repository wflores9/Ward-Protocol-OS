"""Versioned Ward conformance rule definitions.

Certificates pin a version from ``CONFORMANCE_RULE_SET_REGISTRY``. Resolvers
must load that pin instead of silently using whichever rules happen to be
current in the checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, TypedDict

from ward.constants import (
    CLAIM_RATE_LIMIT_MAX,
    CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    MIN_COVERAGE_RATIO,
    WARD_POLICY_TAXON,
)

COVENANT_RULE_SET_VERSION = "ward-conformance-rules/v1"


class ConformanceRule(TypedDict):
    number: int
    label: str
    purpose: str
    primary_inputs: tuple[str, ...]
    deterministic_rule: str
    rejection_boundary: str


@dataclass(frozen=True)
class ConformanceRuleSet:
    """Immutable executable policy values and public rule descriptions."""

    version: str
    rules: tuple[ConformanceRule, ...]
    policy_taxon: int
    claim_rate_limit_max: int
    claim_rate_limit_window_seconds: int
    minimum_coverage_ratio: float


WARD_CONFORMANCE_RULES_V1: tuple[ConformanceRule, ...] = (
    {
        "number": 1,
        "label": "Policy NFT located",
        "purpose": (
            "Prove the claimant currently presents a Ward policy NFT with "
            "the canonical policy taxon."
        ),
        "primary_inputs": ("claimant_address", "nft_token_id"),
        "deterministic_rule": (
            "Scan AccountNFTs for nft_token_id and require NFTokenTaxon "
            f"== {WARD_POLICY_TAXON}."
        ),
        "rejection_boundary": (
            "Reject when the NFT is missing or has a non-Ward taxon."
        ),
    },
    {
        "number": 2,
        "label": "Coverage and premium confirmed",
        "purpose": (
            "Bind policy coverage to immutable NFT URI data and prove the "
            "premium memo reached the pool."
        ),
        "primary_inputs": (
            "policy NFT URI",
            "claimant_address",
            "pool_address",
            "pinned premium transaction hash",
            "Tx",
        ),
        "deterministic_rule": (
            "Decode ward-v2 NFT metadata, require a live expiry, derive "
            "coverage_drops from field c, fetch the pinned premium "
            "transaction by field p, and require a validated tesSUCCESS "
            "Payment whose ward/policy-premium memo binds the claimant, "
            "pool, canonical policy commitment, and coverage."
        ),
        "rejection_boundary": (
            "Reject on legacy or malformed metadata, missing transaction "
            "hash, unvalidated or failed payment, or a mismatched premium "
            "memo."
        ),
    },
    {
        "number": 3,
        "label": "Vault binding verified",
        "purpose": "Prevent cross-vault claims.",
        "primary_inputs": ("policy NFT URI", "defaulted_vault"),
        "deterministic_rule": (
            "Require the policy vault field v or vault_address to equal "
            "defaulted_vault."
        ),
        "rejection_boundary": ("Reject when the policy covers a different vault."),
    },
    {
        "number": 4,
        "label": "Default signal verified",
        "purpose": (
            "Derive default readiness and net depositor loss from the loan "
            "and broker ledger objects."
        ),
        "primary_inputs": (
            "loan_id",
            "Loan ledger object",
            "LoanBroker ledger object",
            "ledger close time",
        ),
        "deterministic_rule": (
            "Accept an on-chain lsfLoanDefault flag, or before default "
            "submission require ledger_time >= NextPaymentDueDate + "
            "GracePeriod and positive TotalValueOutstanding. Net loss is "
            "gross loan value minus first-loss capital absorbed by "
            "LoanBroker cover."
        ),
        "rejection_boundary": (
            "Reject when the default flag/readiness is absent or the "
            "derived net loss is zero."
        ),
    },
    {
        "number": 5,
        "label": "Loss math bounded",
        "purpose": ("Keep payout bounded by actual loss and policy coverage."),
        "primary_inputs": ("net_depositor_loss", "coverage_drops"),
        "deterministic_rule": (
            "Require net_depositor_loss > 0 and set payout = "
            "min(net_depositor_loss, coverage_drops)."
        ),
        "rejection_boundary": (
            "Reject when loss is not positive; never approve payout above "
            "loss or coverage."
        ),
    },
    {
        "number": 6,
        "label": "Coverage pool solvent",
        "purpose": (
            "Prove the pool has enough usable balance before a claim can proceed."
        ),
        "primary_inputs": (
            "pool AccountInfo",
            "FeeSettings at evaluation pin",
            "defaulted_vault",
            "net_depositor_loss",
        ),
        "deterministic_rule": (
            "Read ReserveBase and ReserveIncrement from FeeSettings at the "
            "evaluation pin, compute usable drops as Balance minus "
            "ReserveBase minus OwnerCount*ReserveIncrement, and require "
            "usable >= net_depositor_loss."
        ),
        "rejection_boundary": (
            "Reject when AccountInfo is unavailable, FeeSettings is missing "
            "or not pinned to the evaluation ledger, usable balance is "
            "negative, or usable balance is below the loss."
        ),
    },
    {
        "number": 7,
        "label": "Policy still live",
        "purpose": ("Prevent replay with a burned or unavailable policy NFT."),
        "primary_inputs": ("claimant AccountNFTs", "nft_token_id"),
        "deterministic_rule": (
            "Reuse the Step 1 NFT read and require the policy NFT still exists."
        ),
        "rejection_boundary": (
            "Reject when the NFT is missing or taxon-mismatched at validation time."
        ),
    },
    {
        "number": 8,
        "label": "Claimant ownership proven",
        "purpose": (
            "Prove the claimant still controls the policy NFT used for the claim."
        ),
        "primary_inputs": (
            "claimant AccountNFTs",
            "claimant_address",
            "nft_token_id",
        ),
        "deterministic_rule": (
            "Require the claimant account's NFT set to contain the policy "
            "NFT at validation time."
        ),
        "rejection_boundary": (
            "Reject when the claimant does not currently hold the NFT."
        ),
    },
    {
        "number": 9,
        "label": "Pool solvency and rate limits",
        "purpose": (
            "Avoid repeated claim-window consumption and enforce the final "
            "solvency ratio."
        ),
        "primary_inputs": (
            "nft_token_id",
            "pool AccountInfo",
            "FeeSettings at evaluation pin",
            "payout",
        ),
        "deterministic_rule": (
            f"Allow at most {CLAIM_RATE_LIMIT_MAX} otherwise-valid claim "
            f"attempts per NFT per {CLAIM_RATE_LIMIT_WINDOW_SECONDS} "
            f"seconds, then require usable/payout >= {MIN_COVERAGE_RATIO} "
            "using FeeSettings reserves at the evaluation pin."
        ),
        "rejection_boundary": (
            "Reject when rate limit is exceeded, pool data is unavailable, "
            "FeeSettings is missing or unpinned, usable balance is below "
            "payout, or coverage ratio is too low."
        ),
    },
)

_RULE_SET_V1 = ConformanceRuleSet(
    version=COVENANT_RULE_SET_VERSION,
    rules=WARD_CONFORMANCE_RULES_V1,
    policy_taxon=WARD_POLICY_TAXON,
    claim_rate_limit_max=CLAIM_RATE_LIMIT_MAX,
    claim_rate_limit_window_seconds=CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    minimum_coverage_ratio=MIN_COVERAGE_RATIO,
)

CONFORMANCE_RULE_SET_REGISTRY: Mapping[str, ConformanceRuleSet] = MappingProxyType(
    {COVENANT_RULE_SET_VERSION: _RULE_SET_V1}
)


def load_conformance_rule_set(version: str) -> ConformanceRuleSet:
    """Load exactly the pinned version; missing and unknown pins fail closed."""

    if not isinstance(version, str) or not version.strip():
        raise ValueError("covenant_rule_set_version is required")
    try:
        return CONFORMANCE_RULE_SET_REGISTRY[version]
    except KeyError as exc:
        raise ValueError(f"unsupported covenant_rule_set_version: {version}") from exc


# Backward-compatible aliases for code that emits labels but is not resolving a
# newly pinned certificate. New issuance must stamp COVENANT_RULE_SET_VERSION.
WARD_CONFORMANCE_RULES = WARD_CONFORMANCE_RULES_V1
CHECK_LABELS: dict[int, str] = {
    rule["number"]: rule["label"] for rule in WARD_CONFORMANCE_RULES
}
