#!/usr/bin/env python3
"""Offline replay of archived Devnet observations, never live provenance proof.

Only derives the explicitly listed checks. Archive hashes establish byte identity
against the repository index, not authenticity of the original RPC provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("docs/security/evidence/certificate-index.json")


def replay_certificate(certificate: dict, root: Path = ROOT) -> dict:
    report = {
        "certificate_id": certificate["certificate_id"],
        "mode": "offline_archived_observations",
        "live_provenance_verified": False,
        "independently_verified": False,
        "ward_signed": False,
        "checks": {},
        "limitations": [
            "No network query or third-party attestation was performed.",
            "Archive byte integrity does not authenticate ledger provenance.",
            "Historical claim-attempt history and rate limits are not replayed.",
            "This replays selected semantics, not all nine historical checks or settlement.",
        ],
    }
    ref = certificate.get("raw_reads_archive")
    if ref is None:
        return {
            **report,
            "status": "unavailable",
            "reason": "No issuance archive exists.",
        }
    try:
        path = (root / ref["repo_path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("archive path escapes repository")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        report["archive_sha256"] = digest
        if digest != ref["sha256"]:
            raise ValueError("archive SHA-256 mismatch")
        archive = json.loads(raw)
        if archive["schema"] != "ward-raw-ledger-reads/v1":
            raise ValueError("unsupported archive schema")
        if archive["network"]["ledger_index"] != certificate["network"]["ledger_index"]:
            raise ValueError("archive issuance ledger mismatch")
        reads = [r for r in archive["reads"] if r["source"] == "canonical_validator"]
        if not reads:
            raise ValueError("no canonical observations archived")

        def observation(method, **selectors):
            matches = [
                r
                for r in reads
                if r["request"].get("method") == method
                and all(r["request"].get(k) == v for k, v in selectors.items())
            ]
            if not matches:
                raise ValueError(f"missing archived {method} observation")
            results = [r["response"]["result"] for r in matches]
            if any(result != results[0] for result in results):
                raise ValueError(f"conflicting archived {method} observations")
            if results[0].get("error"):
                raise ValueError(f"archived {method} contains RPC error")
            return results[0]

        objects = {o["label"]: o["identifier"] for o in certificate["objects"]}
        claimant, pool = objects["Borrower / claimant"], objects["Ward pool"]
        loan = observation("ledger_entry", index=objects["Loan"])["node"]
        broker = observation("ledger_entry", index=objects["LoanBroker"])["node"]
        nfts = observation("account_nfts", account=claimant)
        nft = next(
            n for n in nfts["account_nfts"] if n["NFTokenID"] == objects["Policy NFT"]
        )
        policy = json.loads(bytes.fromhex(nft["URI"]).decode())
        ledger = observation("ledger")
        close_time = int(ledger["ledger"]["close_time"])
        loss, coverage = int(loan["TotalValueOutstanding"]), int(policy["c"])
        payout = min(loss, coverage)
        balance = observation("account_info", account=pool)["account_data"]
        expected = certificate["result"]
        checks = report["checks"]
        checks["policy_ownership_taxon"] = (
            nfts["account"] == claimant and nft["NFTokenTaxon"] == 281
        )
        checks["policy_binding"] = (
            policy["w"] in ("ward-v1", "ward-v2")
            and policy["v"] == objects["Defaulted vault owner"]
            and policy["pa"] == pool
        )
        checks["loan_broker_binding"] = (
            loan["LoanBrokerID"] == objects["LoanBroker"]
            and broker["VaultID"] == objects["Vault"]
            and loan["Borrower"] == claimant
        )
        checks["policy_unexpired"] = close_time < int(policy["e"])
        checks["default_ready"] = close_time >= int(loan["NextPaymentDueDate"]) + int(
            loan["GracePeriod"]
        )
        checks["bounded_payout"] = (
            0 < payout <= coverage
            and payout == expected["claim_payout_drops"]
            and loss == expected["vault_loss_drops"]
            and coverage == expected["policy_coverage_drops"]
        )
        checks["pool_balance_covers_payout"] = (
            balance["Account"] == pool and int(balance["Balance"]) >= payout
        )
        premium_reads = [r for r in reads if r["request"].get("method") == "tx"]
        if len(premium_reads) != 1:
            raise ValueError("expected exactly one premium transaction observation")
        premium_result = observation(
            "tx", transaction=premium_reads[0]["request"]["transaction"]
        )
        premium = premium_result.get("tx_json", premium_result)
        memos = [m["Memo"] for m in premium.get("Memos", [])]
        checks["premium_transaction_binding"] = (
            premium_result["meta"]["TransactionResult"] == "tesSUCCESS"
            and premium["TransactionType"] == "Payment"
            and premium["Account"] == claimant
            and premium["Destination"] == pool
            and int(premium.get("Amount", premium.get("DeliverMax"))) > 0
            and premium_result["hash"] == premium_reads[0]["request"]["transaction"]
            and (
                policy["p"] == premium_result["hash"]
                if policy["w"] == "ward-v2"
                else True
            )
            and any(
                bytes.fromhex(m.get("MemoType", "")).decode() == "ward/policy-premium"
                and (
                    bytes.fromhex(m.get("MemoData", ""))
                    .decode()
                    .endswith(f":{coverage}")
                    if policy["w"] == "ward-v2"
                    else bytes.fromhex(m.get("MemoData", "")).decode()
                    == f"{objects['Policy NFT']}:{coverage}"
                )
                for m in memos
            )
        )
        if policy["w"] == "ward-v2":
            report["limitations"].append(
                "ward-v2 replay follows the policy URI premium transaction reference; the pre-mint memo does not bind the later NFT ID. This is not a pass of the current ward-v1 NFT memo rule."
            )
        pin = certificate.get("evaluation_pin")
        if pin:
            state_reads = [r for r in reads if r["request"].get("method") != "tx"]
            checks["evaluation_pin_consistent"] = (
                all(
                    r["request"].get("ledger_index") == pin["ledger_index"]
                    and r["response"]["result"].get("ledger_index")
                    == pin["ledger_index"]
                    and r["response"]["result"].get("ledger_hash") == pin["ledger_hash"]
                    and r["response"]["result"].get("validated") is True
                    for r in state_reads
                )
                and close_time == pin["close_time"]
            )
        else:
            report["limitations"].append(
                "Historical observations lack a consistent evaluation pin; pin provenance is not established."
            )
        fee_reads = [r for r in reads if r["request"].get("fee") is True]
        if fee_reads:
            fees = observation("ledger_entry", fee=True)["node"]
            usable = (
                int(balance["Balance"])
                - int(fees["ReserveBase"])
                - int(balance["OwnerCount"]) * int(fees["ReserveIncrement"])
            )
            checks["reserve_adjusted_solvency"] = (
                fees["LedgerEntryType"] == "FeeSettings" and usable * 2 >= payout * 3
            )
            report["pool_usable_balance_drops"] = usable
        else:
            report["limitations"].append(
                "No pinned FeeSettings observation; reserve-adjusted solvency is not replayed."
            )
        report["derived"] = {
            "loss_drops": loss,
            "coverage_drops": coverage,
            "payout_drops": payout,
            "evaluation_close_time": close_time,
        }
        report["status"] = (
            "replayed_with_limitations" if all(checks.values()) else "failed"
        )
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        report.update(
            status="failed", reason=str(exc) or "required observation missing"
        )
    return report


def replay_index(index: dict, root: Path = ROOT) -> dict:
    certificates = index["certificates"]
    if not isinstance(certificates, list) or not certificates:
        raise ValueError("certificate index must contain a nonempty list")
    reports = [replay_certificate(c, root) for c in certificates]
    return {
        "schema": "ward-offline-devnet-replay/v1",
        "certificates": reports,
        "summary": {
            s: sum(r["status"] == s for r in reports)
            for s in ("replayed_with_limitations", "unavailable", "failed")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=ROOT / INDEX)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Also fail on unavailable legacy archives",
    )
    args = parser.parse_args()
    report = replay_index(json.loads(args.index.read_text()))
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text, end="")
    return int(
        bool(
            report["summary"]["failed"]
            or (args.require_all and report["summary"]["unavailable"])
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
