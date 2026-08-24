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
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ward.conformance_rules import CHECK_LABELS  # noqa: E402
from ward.resolution import UnsignedAction  # noqa: E402
from ward.resolver import Resolver  # noqa: E402

DEVNET_WS = "wss://s.devnet.rippletest.net:51233"
DEVNET_JSON_RPC = "https://s.devnet.rippletest.net:51234"
UNPROVIDED = "UNPROVIDED_BY_LIFECYCLE_RUN"
RAW_READS_SCHEMA = "ward-raw-ledger-reads/v1"


def _jsonable(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _jsonable(to_dict())
    if isinstance(value, dict):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class _RecordingJsonRpcClient:
    def __init__(self, url: str, reads: list[dict[str, Any]]) -> None:
        from xrpl.asyncio.clients import AsyncJsonRpcClient

        self._client = AsyncJsonRpcClient(url)
        self._reads = reads

    async def request(self, request: Any) -> Any:
        record = {
            "source": "canonical_validator",
            "transport": "json-rpc",
            "request": _jsonable(request),
            "claims": ["ward_result"],
        }
        try:
            response = await self._client.request(request)
            record["response"] = _jsonable(response)
            return response
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            self._reads.append(record)

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            result = close()
            if asyncio.iscoroutine(result):
                await result


def _capture_lifecycle_reads(
    lifecycle: dict[str, Any], lifecycle_path: Path, reads: list[dict[str, Any]]
) -> None:
    for raw_read in lifecycle.get("raw_reads", []):
        if not isinstance(raw_read, dict):
            continue
        source = str(raw_read.get("source", "unknown"))
        reads.append(
            {
                **_jsonable(raw_read),
                "source": f"lifecycle.raw_reads.{source}",
                "artifact": str(lifecycle_path),
                "claims": raw_read.get("claims", ["lifecycle_ground_truth"]),
            }
        )

    for label, result in lifecycle.get("tx_results", {}).items():
        if not isinstance(result, dict):
            continue
        raw = result.get("raw")
        if not isinstance(raw, dict) or not raw:
            continue
        reads.append(
            {
                "source": f"lifecycle.tx_results.{label}.raw",
                "transport": "archived-rpc-response",
                "request": {
                    "artifact": str(lifecycle_path),
                    "json_path": f"$.tx_results.{label}.raw",
                    "transaction_hash": result.get("hash"),
                },
                "response": _jsonable(raw),
                "claims": [f"transactions.{label}"],
            }
        )

    for label, raw in lifecycle.get("ledger_objects", {}).items():
        if not isinstance(raw, dict) or not raw:
            continue
        reads.append(
            {
                "source": f"lifecycle.ledger_objects.{label}",
                "transport": "archived-ledger-response",
                "request": {
                    "artifact": str(lifecycle_path),
                    "json_path": f"$.ledger_objects.{label}",
                },
                "response": _jsonable(raw),
                "claims": [f"objects.{label}"],
            }
        )


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
    indexes = [
        tx.get("ledger_index")
        for tx in transactions
        if isinstance(tx.get("ledger_index"), int)
    ]
    return max(indexes) if indexes else "unknown"


def _consecutive_steps_passed(checks: list[dict[str, Any]]) -> int:
    passed = 0
    for check in sorted(checks, key=lambda item: item["number"]):
        if check["status"] != "passed":
            break
        passed += 1
    return passed


async def _read_devnet_loan(
    loan_id: str, reads: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    if not loan_id:
        return None
    from xrpl.asyncio.clients import AsyncWebsocketClient
    from xrpl.models import LedgerEntry

    request = LedgerEntry(index=loan_id)
    record = {
        "source": "devnet_loan_lookup",
        "transport": "websocket",
        "request": _jsonable(request),
        "claims": ["objects.loan_id", "ward_result.checks.4"],
    }
    try:
        async with AsyncWebsocketClient(DEVNET_WS) as client:
            response = await client.request(request)
            record["response"] = _jsonable(response)
            if not response.is_successful():
                return None
            return response.result.get("node")
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return None
    finally:
        if reads is not None:
            reads.append(record)


def _checks(
    *, complete_inputs: bool, loan_node: dict[str, Any] | None
) -> list[dict[str, Any]]:
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
                "detail": (
                    "Loan object was read from Devnet after LoanManage retry."
                    if loan_node
                    else "Loan object could not be re-read from Devnet."
                ),
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
            detail = (
                result.rejection_reason
                or "Canonical Ward validator rejected this check."
            )
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


async def _run_canonical_validation(
    inputs: argparse.Namespace, loan_id: str, reads: list[dict[str, Any]]
):
    from ward.validator import ClaimValidator

    class ArchivingClaimValidator(ClaimValidator):
        def _create_client(self):
            return _RecordingJsonRpcClient(self._url, reads)

    validator = ArchivingClaimValidator(url=inputs.xrpl_json_rpc_url)
    return await validator.validate_claim(
        claimant_address=inputs.claimant_address,
        nft_token_id=inputs.policy_nft_id,
        defaulted_vault=inputs.defaulted_vault,
        loan_id=loan_id,
        pool_address=inputs.pool_address,
    )


async def _build_unsigned_settlement_packet(
    *, inputs: Any, loan_id: str, validation_result: Any
) -> dict[str, Any]:
    """Build the packet for an approved claim without signing or submitting it."""

    payout_drops = int(getattr(validation_result, "claim_payout_drops", 0))
    if payout_drops <= 0:
        raise SystemExit(
            "Refusing to issue approved Devnet evidence without a positive claim payout."
        )

    resolver = Resolver(url=inputs.xrpl_json_rpc_url)
    unsigned_tx = await resolver.build_unsigned_tx(
        pool_address=inputs.pool_address,
        claimant_address=inputs.claimant_address,
        payout_drops=payout_drops,
        collateral_asset={"currency": "XRP"},
        payout_asset={"currency": "XRP"},
    )
    if unsigned_tx.ward_signed is not False:
        raise SystemExit(
            "Refusing to issue evidence: settlement packet was signed by Ward."
        )

    binding = json.dumps(
        {
            "loan_id": loan_id,
            "policy_nft_id": inputs.policy_nft_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    payload: dict[str, Any] = {
        "TransactionType": unsigned_tx.tx_type,
        "Account": unsigned_tx.account,
        "Destination": unsigned_tx.destination,
        "Amount": str(unsigned_tx.amount_drops),
        "Memos": [
            {
                "Memo": {
                    "MemoType": "ward.xls66.default_resolution".encode().hex(),
                    "MemoData": binding.encode().hex(),
                }
            }
        ],
    }
    if unsigned_tx.paths:
        payload["Paths"] = unsigned_tx.paths
    if unsigned_tx.send_max:
        payload["SendMax"] = unsigned_tx.send_max

    return UnsignedAction(
        action_type="xrpl.pool_release",
        rail="xrpl",
        signer=inputs.pool_address,
        payload=payload,
    ).to_dict()


async def build_bundle(
    args: argparse.Namespace, raw_reads: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    lifecycle = json.loads(args.lifecycle.read_text(encoding="utf-8"))
    reads = raw_reads if raw_reads is not None else []
    _capture_lifecycle_reads(lifecycle, args.lifecycle, reads)
    transactions = _tx_rows(lifecycle)
    loan_id = args.loan_id or _find_loan_id(lifecycle)
    loan_node = await _read_devnet_loan(loan_id, reads) if args.query_devnet else None

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
        validation_result = await _run_canonical_validation(
            effective_inputs, loan_id, reads
        )
        checks = _checks_from_validation(validation_result)
        steps_passed = validation_result.steps_passed
        approved = validation_result.approved
        rejection_reason = validation_result.rejection_reason
    else:
        checks = _checks(complete_inputs=complete_inputs, loan_node=loan_node)
        steps_passed = _consecutive_steps_passed(checks)
        approved = False
        rejection_reason = (
            "No Ward policy NFT was supplied; lifecycle ground truth only."
        )

    unsigned_packet = None
    if approved:
        unsigned_packet = await _build_unsigned_settlement_packet(
            inputs=effective_inputs,
            loan_id=loan_id,
            validation_result=validation_result,
        )
        if unsigned_packet is None:
            raise SystemExit(
                "Refusing to issue approved Devnet evidence without an unsigned settlement packet."
            )

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
            "policy_coverage_drops": getattr(
                validation_result, "policy_coverage_drops", 0
            ),
            "checks": checks,
            "settlement": {
                "unsigned_packet_present": unsigned_packet is not None,
                "unsigned_packet": unsigned_packet,
                "signed_by_ward": False,
            },
        },
    }


def _raw_reads_archive_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.raw-reads.json")


def _build_raw_reads_archive(
    *,
    bundle: dict[str, Any],
    args: argparse.Namespace,
    reads: list[dict[str, Any]],
) -> dict[str, Any]:
    sources = {str(read.get("source")) for read in reads}
    required_transactions = [
        str(transaction["type"]) for transaction in bundle.get("transactions", [])
    ]
    archived_transactions = sorted(
        source.removeprefix("lifecycle.tx_results.").removesuffix(".raw")
        for source in sources
        if source.startswith("lifecycle.tx_results.") and source.endswith(".raw")
    )

    required_objects: list[str] = []
    if bundle.get("objects", {}).get("vault_id") != UNPROVIDED:
        required_objects.append("Vault")
    if bundle.get("objects", {}).get("loan_broker_id") != UNPROVIDED:
        required_objects.append("LoanBroker")
    archived_objects = sorted(
        source.removeprefix("lifecycle.ledger_objects.")
        for source in sources
        if source.startswith("lifecycle.ledger_objects.")
    )
    required_query_sources: list[str] = []
    if "Vault" in required_objects:
        required_query_sources.append("vault_account_objects")
    if "LoanBroker" in required_objects:
        required_query_sources.append("loan_broker_account_objects")
    archived_query_sources = sorted(
        source.removeprefix("lifecycle.raw_reads.")
        for read in reads
        if (source := str(read.get("source"))).startswith("lifecycle.raw_reads.")
        and isinstance(read.get("response"), dict)
        and bool(read["response"])
    )

    errors: list[str] = []
    missing_transactions = sorted(
        set(required_transactions) - set(archived_transactions)
    )
    if missing_transactions:
        errors.append(
            "missing raw transaction responses: " + ", ".join(missing_transactions)
        )
    missing_objects = sorted(set(required_objects) - set(archived_objects))
    if missing_objects:
        errors.append("missing raw ledger object reads: " + ", ".join(missing_objects))
    missing_queries = sorted(set(required_query_sources) - set(archived_query_sources))
    if missing_queries:
        errors.append(
            "missing full lifecycle RPC/WS responses: " + ", ".join(missing_queries)
        )

    canonical_required = bool(bundle.get("source", {}).get("complete_ward_inputs"))
    canonical_reads = sum(
        1 for read in reads if read.get("source") == "canonical_validator"
    )
    if canonical_required and canonical_reads == 0:
        errors.append("canonical validation completed without any archived RPC reads")

    loan_lookup_required = bool(
        args.query_devnet and bundle["objects"]["loan_id"] != UNPROVIDED
    )
    loan_lookup_reads = sum(
        1 for read in reads if read.get("source") == "devnet_loan_lookup"
    )
    if loan_lookup_required and loan_lookup_reads == 0:
        errors.append("Devnet loan lookup was requested but not archived")

    return {
        "schema": RAW_READS_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "certificate_file": args.out.name,
        "network": bundle.get("network"),
        "reads": reads,
        "completeness": {
            "required_transaction_types": required_transactions,
            "archived_transaction_types": archived_transactions,
            "required_lifecycle_objects": required_objects,
            "archived_lifecycle_objects": archived_objects,
            "required_lifecycle_query_sources": required_query_sources,
            "archived_lifecycle_query_sources": archived_query_sources,
            "canonical_rpc_reads_required": canonical_required,
            "canonical_rpc_reads_archived": canonical_reads,
            "devnet_loan_lookup_required": loan_lookup_required,
            "devnet_loan_lookup_reads_archived": loan_lookup_reads,
            "errors": errors,
            "complete": not errors,
        },
    }


def _atomic_write_pair(
    output_path: Path,
    output_text: str,
    archive_path: Path,
    archive_text: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    output_tmp = output_path.with_name(f".{output_path.name}.tmp")
    archive_tmp = archive_path.with_name(f".{archive_path.name}.tmp")
    try:
        archive_tmp.write_text(archive_text, encoding="utf-8")
        output_tmp.write_text(output_text, encoding="utf-8")
        os.replace(archive_tmp, archive_path)
        os.replace(output_tmp, output_path)
    finally:
        output_tmp.unlink(missing_ok=True)
        archive_tmp.unlink(missing_ok=True)


async def issue_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    raw_reads: list[dict[str, Any]] = []
    bundle = await build_bundle(args, raw_reads)
    archive = _build_raw_reads_archive(bundle=bundle, args=args, reads=raw_reads)
    completeness = archive["completeness"]
    if not completeness["complete"]:
        details = "; ".join(completeness["errors"])
        raise SystemExit(
            "Refusing to issue non-mainnet evidence without a complete raw-read "
            f"archive: {details}"
        )

    archive_path = _raw_reads_archive_path(args.out)
    archive_text = json.dumps(archive, indent=2, ensure_ascii=False) + "\n"
    bundle["source"]["raw_reads_archive"] = {
        "file": archive_path.name,
        "schema": RAW_READS_SCHEMA,
        "sha256": hashlib.sha256(archive_text.encode("utf-8")).hexdigest(),
        "complete": True,
    }
    bundle_text = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_pair(args.out, bundle_text, archive_path, archive_text)
    return bundle, archive_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "lifecycle", type=Path, help="phase1_devnet_xls6566.py JSON output"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Evidence bundle output path"
    )
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
    bundle, archive_path = asyncio.run(issue_evidence(args))
    print(f"Wrote evidence bundle: {args.out}")
    print(f"Wrote required raw-read archive: {archive_path}")
    if not bundle["source"]["complete_ward_inputs"]:
        print("Bundle is fail-closed: Ward policy NFT/pool inputs were not supplied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
