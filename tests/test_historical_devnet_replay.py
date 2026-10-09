import hashlib
import json
import subprocess
import sys
from copy import deepcopy

import pytest

from scripts.replay_historical_devnet import (
    INDEX,
    ROOT,
    replay_certificate,
    replay_index,
)


def entries():
    return json.loads((ROOT / INDEX).read_text())["certificates"]


def test_replay_does_not_claim_live_verification():
    report = replay_index({"certificates": entries()})
    assert report["summary"] == {
        "replayed_with_limitations": 2,
        "unavailable": 1,
        "failed": 0,
    }
    for item in report["certificates"]:
        assert item["live_provenance_verified"] is False
        assert item["independently_verified"] is False
        assert item["ward_signed"] is False
    assert "No issuance archive" in report["certificates"][0]["reason"]
    assert report["certificates"][2]["pool_usable_balance_drops"] == 99_000_001
    assert any("FeeSettings" in s for s in report["certificates"][1]["limitations"])
    assert any("pre-mint memo" in s for s in report["certificates"][2]["limitations"])


def test_archive_byte_tampering_fails(tmp_path):
    certificate = deepcopy(entries()[2])
    ref = certificate["raw_reads_archive"]
    raw = (ROOT / ref["repo_path"]).read_bytes() + b" "
    ref["repo_path"] = "archive.json"
    (tmp_path / "archive.json").write_bytes(raw)
    report = replay_certificate(certificate, tmp_path)
    assert report["status"] == "failed"
    assert "SHA-256 mismatch" in report["reason"]


@pytest.mark.parametrize(
    "mutation",
    ["payout", "pin", "missing", "conflicting", "premium", "owner", "reserve"],
)
def test_semantic_tampering_fails_even_with_matching_digest(tmp_path, mutation):
    certificate = deepcopy(entries()[2])
    ref = certificate["raw_reads_archive"]
    archive = json.loads((ROOT / ref["repo_path"]).read_text())
    reads = [r for r in archive["reads"] if r["source"] == "canonical_validator"]
    if mutation == "payout":
        certificate["result"]["claim_payout_drops"] += 1
    elif mutation == "pin":
        reads[0]["response"]["result"]["ledger_hash"] = "0" * 64
    elif mutation == "missing":
        archive["reads"] = [
            r for r in archive["reads"] if r["request"].get("method") != "account_nfts"
        ]
    elif mutation == "conflicting":
        extra = deepcopy(reads[0])
        extra["response"]["result"]["ledger"]["close_time"] += 1
        archive["reads"].append(extra)
    elif mutation == "premium":
        next(r for r in reads if r["request"].get("method") == "tx")["response"][
            "result"
        ]["tx_json"]["Destination"] = "wrong"
    elif mutation == "owner":
        next(r for r in reads if r["request"].get("method") == "account_nfts")[
            "response"
        ]["result"]["account"] = "wrong"
    elif mutation == "reserve":
        next(r for r in reads if r["request"].get("fee"))["response"]["result"]["node"][
            "ReserveBase"
        ] = 200_000_000
    raw = json.dumps(archive).encode()
    ref.update(repo_path="archive.json", sha256=hashlib.sha256(raw).hexdigest())
    (tmp_path / "archive.json").write_bytes(raw)
    assert replay_certificate(certificate, tmp_path)["status"] == "failed"


def test_refuses_archive_outside_repository(tmp_path):
    certificate = deepcopy(entries()[2])
    certificate["raw_reads_archive"]["repo_path"] = "../outside.json"
    assert "escapes repository" in replay_certificate(certificate, tmp_path)["reason"]


def test_require_all_does_not_hide_missing_legacy_archive():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/replay_historical_devnet.py"),
            "--require-all",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["summary"]["unavailable"] == 1
