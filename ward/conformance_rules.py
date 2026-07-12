"""Ward conformance rule definitions.

This module is the public, machine-readable surface for the nine Ward claim
validation checks. Keep these definitions aligned with ``ward.validator`` so
external reviewers can map evidence bundles back to the rules they verify.
"""

from __future__ import annotations

from typing import TypedDict

from ward.constants import (
    CLAIM_RATE_LIMIT_MAX,
    CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    MIN_COVERAGE_RATIO,
    WARD_POLICY_TAXON,
    XRPL_BASE_RESERVE_DROPS,
    XRPL_OWNER_RESERVE_DROPS,
)


class ConformanceRule(TypedDict):
    number: int
    label: str
    purpose: str
    primary_inputs: tuple[str, ...]
    deterministic_rule: str
    rejection_boundary: str


WARD_CONFORMANCE_RULES: tuple[ConformanceRule, ...] = (
    {
        "number": 1,
        "label": "Policy NFT located",
        "purpose": "Prove the claimant currently presents a Ward policy NFT with the canonical policy taxon.",
        "primary_inputs": ("claimant_address", "nft_token_id"),
        "deterministic_rule": (
            f"Scan AccountNFTs for nft_token_id and require NFTokenTaxon == {WARD_POLICY_TAXON}."
        ),
        "rejection_boundary": "Reject when the NFT is missing or has a non-Ward taxon.",
    },
    {
        "number": 2,
        "label": "Coverage and premium confirmed",
        "purpose": "Bind policy coverage to immutable NFT URI data and prove the premium memo reached the pool.",
        "primary_inputs": ("policy NFT URI", "claimant_address", "pool_address", "AccountTx"),
        "deterministic_rule": (
            "Decode the NFT URI, require a live expiry, derive coverage_drops from field c "
            "or coverage_drops, and find a matching ward/policy-premium payment memo "
            "for claimant, pool, policy NFT, and coverage."
        ),
        "rejection_boundary": "Reject on missing/expired metadata, non-positive coverage, or missing premium memo.",
    },
    {
        "number": 3,
        "label": "Vault binding verified",
        "purpose": "Prevent cross-vault claims.",
        "primary_inputs": ("policy NFT URI", "defaulted_vault"),
        "deterministic_rule": "Require the policy vault field v or vault_address to equal defaulted_vault.",
        "rejection_boundary": "Reject when the policy covers a different vault.",
    },
    {
        "number": 4,
        "label": "Default signal verified",
        "purpose": "Derive default readiness and net depositor loss from the loan and broker ledger objects.",
        "primary_inputs": ("loan_id", "Loan ledger object", "LoanBroker ledger object", "ledger close time"),
        "deterministic_rule": (
            "Accept an on-chain lsfLoanDefault flag, or before default submission require "
            "ledger_time >= NextPaymentDueDate + GracePeriod and positive TotalValueOutstanding. "
            "Net loss is gross loan value minus first-loss capital absorbed by LoanBroker cover."
        ),
        "rejection_boundary": "Reject when the default flag/readiness is absent or the derived net loss is zero.",
    },
    {
        "number": 5,
        "label": "Loss math bounded",
        "purpose": "Keep payout bounded by actual loss and policy coverage.",
        "primary_inputs": ("net_depositor_loss", "coverage_drops"),
        "deterministic_rule": "Require net_depositor_loss > 0 and set payout = min(net_depositor_loss, coverage_drops).",
        "rejection_boundary": "Reject when loss is not positive; never approve payout above loss or coverage.",
    },
    {
        "number": 6,
        "label": "Coverage pool solvent",
        "purpose": "Prove the pool has enough usable balance before a claim can proceed.",
        "primary_inputs": ("pool AccountInfo", "defaulted_vault", "net_depositor_loss"),
        "deterministic_rule": (
            "Compute usable drops as Balance - "
            f"({XRPL_BASE_RESERVE_DROPS} + OwnerCount * {XRPL_OWNER_RESERVE_DROPS}) "
            "and require usable >= net_depositor_loss."
        ),
        "rejection_boundary": "Reject when AccountInfo is unavailable, usable balance is negative, or usable balance is below the loss.",
    },
    {
        "number": 7,
        "label": "Policy still live",
        "purpose": "Prevent replay with a burned or unavailable policy NFT.",
        "primary_inputs": ("claimant AccountNFTs", "nft_token_id"),
        "deterministic_rule": "Reuse the Step 1 NFT read and require the policy NFT still exists.",
        "rejection_boundary": "Reject when the NFT is missing or taxon-mismatched at validation time.",
    },
    {
        "number": 8,
        "label": "Claimant ownership proven",
        "purpose": "Prove the claimant still controls the policy NFT used for the claim.",
        "primary_inputs": ("claimant AccountNFTs", "claimant_address", "nft_token_id"),
        "deterministic_rule": "Require the claimant account's NFT set to contain the policy NFT at validation time.",
        "rejection_boundary": "Reject when the claimant does not currently hold the NFT.",
    },
    {
        "number": 9,
        "label": "Pool solvency and rate limits",
        "purpose": "Avoid repeated claim-window consumption and enforce the final solvency ratio.",
        "primary_inputs": ("nft_token_id", "pool AccountInfo", "payout"),
        "deterministic_rule": (
            f"Allow at most {CLAIM_RATE_LIMIT_MAX} otherwise-valid claim attempts per NFT "
            f"per {CLAIM_RATE_LIMIT_WINDOW_SECONDS} seconds, then require usable/payout >= "
            f"{MIN_COVERAGE_RATIO}."
        ),
        "rejection_boundary": "Reject when rate limit is exceeded, pool data is unavailable, usable balance is below payout, or coverage ratio is too low.",
    },
)


CHECK_LABELS: dict[int, str] = {
    rule["number"]: rule["label"] for rule in WARD_CONFORMANCE_RULES
}
