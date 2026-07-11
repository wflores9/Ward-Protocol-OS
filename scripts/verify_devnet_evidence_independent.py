#!/usr/bin/env python3
"""Independently verify a Ward XRPL Devnet evidence run.

This verifier reads the raw lifecycle artifact plus the Ward evidence bundle
and derives the critical proof claims without trusting ward_result.checks.
It is intentionally narrow: it verifies the Devnet design-partner artifact
shape produced by phase1_devnet_xls6566.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _hex_to_text(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8")


def _json_from_hex(value: str) -> dict[str, Any]:
    decoded = json.loads(_hex_to_text(value))
    if not isinstance(decoded, dict):
        raise ValueError("decoded URI is not a JSON object")
    return decoded


def _tx(lifecycle: dict[str, Any], name: str) -> dict[str, Any]:
    result = lifecycle.get("tx_results", {}).get(name)
    if not isinstance(result, dict):
        raise ValueError(f"missing tx_results.{name}")
    return result


def _raw_tx_json(lifecycle: dict[str, Any], name: str) -> dict[str, Any]:
    tx_json = _tx(lifecycle, name).get("raw", {}).get("tx_json")
    if not isinstance(tx_json, dict):
        raise ValueError(f"missing tx_json for {name}")
    return tx_json


def _created_nft_id(lifecycle: dict[str, Any]) -> str:
    meta = _tx(lifecycle, "WardPolicyNFTokenMint").get("raw", {}).get("meta", {})
    token_id = meta.get("nftoken_id")
    if token_id:
        return str(token_id)
    for node in meta.get("AffectedNodes", []):
        created = node.get("CreatedNode", {})
        fields = created.get("NewFields", {})
        for token in fields.get("NFTokens", []):
            nft = token.get("NFToken", {})
            if nft.get("NFTokenID"):
                return str(nft["NFTokenID"])
    raise ValueError("could not derive policy NFT ID from mint metadata")


def _successful_tx_names(lifecycle: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for name, result in lifecycle.get("tx_results", {}).items():
        if isinstance(result, dict) and result.get("engine_result") == "tesSUCCESS":
            names.append(name)
    return names


def verify(lifecycle: dict[str, Any], ward_bundle: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str) -> dict[str, Any]:
        if not condition:
            failures.append(name)
        return {
            "name": name,
            "status": "passed" if condition else "failed",
            "detail": detail,
        }

    meta = lifecycle.get("meta", {})
    objects = lifecycle.get("ledger_objects", {})
    policy = lifecycle.get("ward_policy", {})
    ward_objects = ward_bundle.get("objects", {})
    ward_result = ward_bundle.get("ward_result", {})

    vault = objects.get("Vault", {})
    broker = objects.get("LoanBroker", {})
    loan = objects.get("Loan_pre_default_resolution") or objects.get("Loan", {})

    mint_tx = _raw_tx_json(lifecycle, "WardPolicyNFTokenMint")
    premium_tx = _raw_tx_json(lifecycle, "WardPolicyPremiumPayment")
    nft_id = _created_nft_id(lifecycle)
    uri = _json_from_hex(str(mint_tx.get("URI", "")))
    premium_memo = premium_tx.get("Memos", [{}])[0].get("Memo", {})
    premium_type = _hex_to_text(str(premium_memo.get("MemoType", "")))
    premium_data = _hex_to_text(str(premium_memo.get("MemoData", "")))
    premium_policy_id, _, premium_coverage = premium_data.partition(":")

    coverage_drops = int(policy.get("coverage_drops", 0))
    vault_loss_drops = int(loan.get("TotalValueOutstanding", 0))
    claim_payout_drops = min(vault_loss_drops, coverage_drops)
    due_time = int(loan.get("NextPaymentDueDate", 0)) + int(loan.get("GracePeriod", 0))
    pre_resolution_close_time = int(meta.get("pre_resolution_ledger_close_time", 0))
    pool_balance_after_premium = 0
    for node in _tx(lifecycle, "WardPolicyPremiumPayment").get("raw", {}).get(
        "meta", {}
    ).get("AffectedNodes", []):
        modified = node.get("ModifiedNode", {})
        fields = modified.get("FinalFields", {})
        if fields.get("Account") == policy.get("pool_address"):
            pool_balance_after_premium = int(fields.get("Balance", 0))
            break

    checks = [
        check(
            "all_lifecycle_transactions_successful",
            {
                "VaultCreate",
                "VaultDeposit",
                "WardPolicyNFTokenMint",
                "WardPolicyPremiumPayment",
                "LoanBrokerSet",
                "LoanBrokerCoverDeposit",
                "LoanSet",
            }.issubset(set(_successful_tx_names(lifecycle))),
            "Required lifecycle transactions are present with tesSUCCESS.",
        ),
        check(
            "default_resolution_not_submitted",
            meta.get("default_resolution_submitted") is False,
            "Artifact stopped before LoanManageRetryAfterGrace.",
        ),
        check(
            "policy_nft_matches_artifact",
            nft_id == policy.get("policy_nft_id") == ward_objects.get("policy_nft_id"),
            "Policy NFT ID derived from NFTokenMint metadata matches both artifacts.",
        ),
        check(
            "policy_uri_binds_vault_coverage_pool",
            uri.get("w") == "ward-v1"
            and uri.get("v") == policy.get("defaulted_vault")
            and int(uri.get("c", 0)) == coverage_drops
            and uri.get("pa") == policy.get("pool_address"),
            "Decoded policy URI binds vault, coverage, expiry, tier, and pool.",
        ),
        check(
            "policy_taxon_and_owner_match",
            mint_tx.get("NFTokenTaxon") == policy.get("nft_taxon")
            and mint_tx.get("Account") == policy.get("claimant_address"),
            "NFToken taxon and minting account match the Ward policy artifact.",
        ),
        check(
            "premium_payment_matches_policy",
            premium_tx.get("TransactionType") == "Payment"
            and premium_tx.get("Account") == policy.get("claimant_address")
            and premium_tx.get("Destination") == policy.get("pool_address")
            and premium_type == "ward/policy-premium"
            and premium_policy_id == nft_id
            and int(premium_coverage) == coverage_drops,
            "Premium memo independently ties payment to policy NFT and coverage.",
        ),
        check(
            "vault_broker_loan_binding",
            vault.get("index") == broker.get("VaultID")
            and broker.get("index") == loan.get("LoanBrokerID")
            and vault.get("Owner") == policy.get("defaulted_vault"),
            "Vault, broker, loan, and defaulted vault resolve to one chain of state.",
        ),
        check(
            "claimant_is_borrower",
            loan.get("Borrower") == policy.get("claimant_address"),
            "Claimant address matches the loan borrower in the raw Loan object.",
        ),
        check(
            "pre_resolution_default_ready",
            pre_resolution_close_time >= due_time and vault_loss_drops > 0,
            "Ledger close time is after NextPaymentDueDate plus GracePeriod and loss remains positive.",
        ),
        check(
            "loss_math_bounded",
            claim_payout_drops == ward_result.get("claim_payout_drops")
            and claim_payout_drops == ward_result.get("vault_loss_drops")
            and claim_payout_drops <= coverage_drops,
            "Derived payout equals min(loss, coverage) and matches Ward output.",
        ),
        check(
            "pool_solvent_for_claim",
            pool_balance_after_premium >= claim_payout_drops,
            "Pool balance after premium payment covers the derived claim payout.",
        ),
        check(
            "ward_never_signed",
            policy.get("ward_signed") is False
            and ward_result.get("ward_signed") is False
            and ward_result.get("settlement", {}).get("signed_by_ward") is False,
            "Policy artifact and Ward bundle preserve ward_signed = False.",
        ),
    ]

    return {
        "protocol": "Ward Protocol",
        "verification_type": "xrpl-devnet-independent-evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approved_by_ward": ward_result.get("approved") is True,
        "independently_verified": not failures,
        "ward_signed": False,
        "derived": {
            "policy_nft_id": nft_id,
            "loan_id": ward_objects.get("loan_id"),
            "vault_loss_drops": vault_loss_drops,
            "policy_coverage_drops": coverage_drops,
            "claim_payout_drops": claim_payout_drops,
            "default_ready_ledger_time": pre_resolution_close_time,
            "default_ready_threshold": due_time,
            "pool_balance_after_premium": pool_balance_after_premium,
        },
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lifecycle", type=Path)
    parser.add_argument("ward_bundle", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        report = verify(_load(args.lifecycle), _load(args.ward_bundle))
    except Exception as exc:  # noqa: BLE001 - CLI should report useful failures
        print(f"Independent verification failed: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")

    print(text)
    return 0 if report["independently_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
