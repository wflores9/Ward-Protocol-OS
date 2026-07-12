#!/usr/bin/env python3
"""Build a Ward XRPL Devnet evidence bundle from lifecycle ground truth.

This runner consumes the output produced by `phase1_devnet_xls6566.py`.
It does not sign, submit, or fabricate any result. When a Ward policy NFT and
pool binding are not supplied, it emits a fail-closed bundle only when
`--allow-incomplete` is set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ward.conformance_rules import CHECK_LABELS

DEVNET_WS = "wss://s.devnet.rippletest.net:51233"
DEVNET_JSON_RPC = "https://s.devnet.rippletest.net:51234"
UNPROVIDED = "UNPROVIDED_BY_LIFECYCLE_RUN"

def _git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:  # noqa: BLE001 - evidence should still record uncertainty
        return "unknown"


def _tx_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, result in results.get("tx_results", {}).items():
        engine_result = result.get("engine_result")
        tx_hash = result.get("hash")
        if not tx_hash:
            continue
        raw = result.get("raw", {})
        ledger_index = raw.get("ledger_index") or raw.get("validated_ledger_index")
        rows.append(
            {
                "hash": tx_hash,
                "type": label,
                "ledger_index": ledger_index or "unknown",
                "engine_result": engine_result,
            }
        )
    return rows


def _find_loan_id(results: dict[str, Any]) -> str:
    for node in (
        results.get("tx_results", {})
        .get("LoanSet", {})
        .get("raw", {})
        .get("meta", {})
        .get("AffectedNodes", [])
    ):
        created = node.get("CreatedNode", {})
        if created.get("LedgerEntryType") == "Loan":
            return created.get("LedgerIndex", "")
    return ""


def _final_ledger_index(transactions: list[dict[str, Any]]) -> int | str:
    indexes = [tx.get("ledger_index") for tx in transactions if isinstance(tx.get("ledger_index"), int)]
    return max(indexes) if indexes else "unknown"


def _consecutive_steps_passed(checks: list[dict[str, Any]]) -> int:
    passed = 0
    for check in sorted(checks, key=lambda item: item["number"]):
        if check["status"] != "passed":
            break
        passed += 1
    return passed


async def _read_devnet_loan(loan_id: str) -> dict[str, Any] | None:
    if not loan_id:
        return None
    from xrpl.asyncio.clients import AsyncWebsocketClient
    from xrpl.models import LedgerEntry

    try:
        async with AsyncWebsocketClient(DEVNET_WS) as client:
            response = await client.request(LedgerEntry(index=loan_id))
            if not response.is_successful():
                return None
            return response.result.get("node")
    except Exception:
        return None


def _checks(*, complete_inputs: bool, loan_node: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not complete_inputs:
        return [
            {
                "number": 1,
                "label": "Policy NFT located",
                "status": "failed",
                "detail": "No Ward policy NFT was supplied for this lifecycle-only Devnet run.",
            },
            {
                "number": 2,
                "label": "Coverage and premium confirmed",
                "status": "not_applicable",
                "detail": "Requires a Ward policy NFT and premium memo.",
            },
            {
                "number": 3,
                "label": "Vault binding verified",
                "status": "not_applicable",
                "detail": "Requires Ward policy metadata binding to the Devnet vault.",
            },
            {
                "number": 4,
                "label": "Default signal verified",
                "status": "passed" if loan_node else "not_applicable",
                "detail": "Loan object was read from Devnet after LoanManage retry."
                if loan_node
                else "Loan object could not be re-read from Devnet.",
            },
            {
                "number": 5,
                "label": "Loss math bounded",
                "status": "not_applicable",
                "detail": "Requires Ward policy coverage and pool state.",
            },
            {
                "number": 6,
                "label": "Coverage pool solvent",
                "status": "not_applicable",
                "detail": "Requires Ward pool address and authoritative pool balance.",
            },
            {
                "number": 7,
                "label": "Policy still live",
                "status": "not_applicable",
                "detail": "Requires a Ward policy NFT.",
            },
            {
                "number": 8,
                "label": "Claimant ownership proven",
                "status": "not_applicable",
                "detail": "Requires claimant account and policy NFT ownership.",
            },
            {
                "number": 9,
                "label": "Pool solvency and rate limits",
                "status": "not_applicable",
                "detail": "Requires otherwise-valid claim inputs before consuming the rate-limit window.",
            },
        ]

    return [
        {
            "number": number,
            "label": label,
            "status": "not_applicable",
            "detail": "Canonical online Ward validation was not requested.",
        }
        for number, label in CHECK_LABELS.items()
    ]


def _checks_from_validation(result: Any) -> list[dict[str, Any]]:
    failed_step = None if result.approved else min(max(result.steps_passed + 1, 1), 9)
    checks: list[dict[str, Any]] = []
    for number, label in CHECK_LABELS.items():
        if result.approved or number <= result.steps_passed:
            status = "passed"
            detail = "Canonical Ward validator passed this check."
        elif number == failed_step:
            status = "failed"
            detail = result.rejection_reason or "Canonical Ward validator rejected this check."
        else:
            status = "not_applicable"
            detail = "Earlier canonical Ward check failed."
        checks.append(
            {
                "number": number,
                "label": label,
                "status": status,
                "detail": detail,
            }
        )
    return checks


async def _run_canonical_validation(inputs: argparse.Namespace, loan_id: str):
    from ward.validator import ClaimValidator

    validator = ClaimValidator(url=inputs.xrpl_json_rpc_url)
    return await validator.validate_claim(
        claimant_address=inputs.claimant_address,
        nft_token_id=inputs.policy_nft_id,
        defaulted_vault=inputs.defaulted_vault,
        loan_id=loan_id,
        pool_address=inputs.pool_address,
    )


async def build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    lifecycle = json.loads(args.lifecycle.read_text(encoding="utf-8"))
    transactions = _tx_rows(lifecycle)
    loan_id = args.loan_id or _find_loan_id(lifecycle)
    loan_node = await _read_devnet_loan(loan_id) if args.query_devnet else None

    vault = lifecycle.get("ledger_objects", {}).get("Vault", {})
    broker = lifecycle.get("ledger_objects", {}).get("LoanBroker", {})
    ward_policy = lifecycle.get("ward_policy", {})
    wallets = lifecycle.get("wallets", {})
    effective_inputs = SimpleNamespace(
        policy_nft_id=args.policy_nft_id or ward_policy.get("policy_nft_id"),
        pool_address=args.pool_address or ward_policy.get("pool_address"),
        claimant_address=args.claimant_address
        or ward_policy.get("claimant_address")
        or wallets.get("borrower", {}).get("address"),
        defaulted_vault=args.defaulted_vault
        or ward_policy.get("defaulted_vault")
        or wallets.get("vault_owner", {}).get("address"),
        xrpl_json_rpc_url=args.xrpl_json_rpc_url,
    )
    complete_inputs = all(
        [
            effective_inputs.policy_nft_id,
            effective_inputs.pool_address,
            effective_inputs.claimant_address,
            effective_inputs.defaulted_vault,
        ]
    )
    if not complete_inputs and not args.allow_incomplete:
        raise SystemExit(
            "Incomplete Ward inputs. Provide --policy-nft-id, --pool-address, "
            "--claimant-address, and --defaulted-vault, or pass --allow-incomplete "
            "to emit a fail-closed lifecycle-only bundle."
        )

    validation_result = None
    if complete_inputs:
        validation_result = await _run_canonical_validation(effective_inputs, loan_id)
        checks = _checks_from_validation(validation_result)
        steps_passed = validation_result.steps_passed
        approved = validation_result.approved
        rejection_reason = validation_result.rejection_reason
    else:
        checks = _checks(complete_inputs=complete_inputs, loan_node=loan_node)
        steps_passed = _consecutive_steps_passed(checks)
        approved = False
        rejection_reason = "No Ward policy NFT was supplied; lifecycle ground truth only."

    return {
        "protocol": "Ward Protocol",
        "evidence_type": "xrpl-devnet-lifecycle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "network": {
            "name": "XRPL Devnet",
            "rpc_url": args.xrpl_json_rpc_url if complete_inputs else DEVNET_WS,
            "ws_url": DEVNET_WS,
            "ledger_index": _final_ledger_index(transactions),
        },
        "source": {
            "tool": "scripts/run_xrpl_devnet_evidence.py",
            "lifecycle_artifact": str(args.lifecycle),
            "unaffiliated_reference": True,
            "complete_ward_inputs": complete_inputs,
        },
        "objects": {
            "vault_id": args.vault_id or vault.get("index") or UNPROVIDED,
            "loan_broker_id": args.loan_broker_id or broker.get("index") or UNPROVIDED,
            "loan_id": loan_id or UNPROVIDED,
            "policy_nft_id": effective_inputs.policy_nft_id or UNPROVIDED,
            "pool_address": effective_inputs.pool_address or UNPROVIDED,
            "claimant_address": effective_inputs.claimant_address or UNPROVIDED,
            "defaulted_vault": effective_inputs.defaulted_vault or UNPROVIDED,
        },
        "transactions": transactions,
        "ward_result": {
            "ward_signed": False,
            "approved": approved,
            "steps_passed": steps_passed,
            "rejection_reason": "" if approved else rejection_reason,
            "claim_payout_drops": getattr(validation_result, "claim_payout_drops", 0),
            "vault_loss_drops": getattr(validation_result, "vault_loss_drops", 0),
            "policy_coverage_drops": getattr(validation_result, "policy_coverage_drops", 0),
            "checks": checks,
            "settlement": {
                "unsigned_packet_present": False,
                "signed_by_ward": False,
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lifecycle", type=Path, help="phase1_devnet_xls6566.py JSON output")
    parser.add_argument("--out", type=Path, required=True, help="Evidence bundle output path")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--query-devnet", action="store_true")
    parser.add_argument("--vault-id")
    parser.add_argument("--loan-broker-id")
    parser.add_argument("--loan-id")
    parser.add_argument("--policy-nft-id")
    parser.add_argument("--pool-address")
    parser.add_argument("--claimant-address")
    parser.add_argument("--defaulted-vault")
    parser.add_argument("--xrpl-json-rpc-url", default=DEVNET_JSON_RPC)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = asyncio.run(build_bundle(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"Wrote evidence bundle: {args.out}")
    if not bundle["source"]["complete_ward_inputs"]:
        print("Bundle is fail-closed: Ward policy NFT/pool inputs were not supplied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
