from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_resolution_receipt.py"
MANIFEST = ROOT / "docs" / "security" / "evidence" / "verification-manifest.json"
GOLDEN = ROOT / "docs" / "security" / "evidence" / "conditional-release-golden-receipt.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _receipt_entries() -> list[dict]:
    return list(_manifest()["receipts"])


@pytest.mark.parametrize("entry", _receipt_entries(), ids=lambda entry: entry["name"])
def test_independent_verifier_accepts_manifest_receipts(entry: dict) -> None:
    receipt_path = ROOT / entry["path"]

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(receipt_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    verified = json.loads(result.stdout)
    assert verified["ok"] is True
    assert verified["hash_matches"] is True
    assert verified["ward_signed"] is False
    assert verified["workflow_type"] == entry["workflow_type"]
    assert verified["decision"] == entry["expected_decision"]


def test_verification_manifest_artifacts_exist() -> None:
    manifest = _manifest()
    paths = [
        manifest["schema"],
        manifest["verifier"],
        manifest["review_checklist"],
        manifest["live_smoke_evidence"],
        manifest["live_resolution_case_smoke_evidence"],
        manifest["live_resolution_desk_full_artifact_smoke"],
        manifest["live_netten_resolution_desk_smoke"],
        *[entry["path"] for entry in manifest["receipts"]],
        *[entry["path"] for entry in manifest["review_packets"]],
    ]

    for path in paths:
        assert (ROOT / path).exists(), path


def test_independent_verifier_rejects_tampered_receipt(tmp_path: Path) -> None:
    receipt = json.loads(GOLDEN.read_text(encoding="utf-8"))
    receipt["case"]["metadata"]["ledger_index"] += 1
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(receipt), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tampered)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "receipt_hash mismatch" in result.stderr


def test_independent_verifier_rejects_signed_receipt(tmp_path: Path) -> None:
    receipt = json.loads(GOLDEN.read_text(encoding="utf-8"))
    receipt["ward_signed"] = True
    signed = tmp_path / "signed.json"
    signed.write_text(json.dumps(receipt), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(signed)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "schema validation failed" in result.stderr or "ward_signed must be false" in result.stderr


def test_independent_verifier_rejects_secret_like_receipt_key(tmp_path: Path) -> None:
    receipt = json.loads(GOLDEN.read_text(encoding="utf-8"))
    receipt["case"]["metadata"]["private_key"] = "not-allowed"
    # Keep the original hash on purpose; either schema or hash verification may fail first.
    leaked = tmp_path / "leaked.json"
    leaked.write_text(json.dumps(receipt), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(leaked)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert result.stderr
