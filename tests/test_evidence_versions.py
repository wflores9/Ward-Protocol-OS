"""Append-only evidence guard (evidence changelog).

Every JSON file under docs/security/evidence/devnet/ must hash to a value listed
in docs/security/evidence/evidence-versions.json, and every listed file must
exist with exactly that hash. An in-place edit therefore fails CI unless a new
version entry (and a CHANGELOG entry) is appended. ward_signed = False — always.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/security/evidence"
VERSIONS = EVIDENCE / "evidence-versions.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict:
    return json.loads(VERSIONS.read_text(encoding="utf-8"))


def test_versions_file_is_unsigned_and_append_only_declared() -> None:
    doc = _versions()
    assert doc["schema"] == "ward-evidence-versions/v1"
    assert doc["ward_signed"] is False
    assert "append-only" in doc["rule"]


def test_every_listed_version_exists_with_its_hash() -> None:
    for entry in _versions()["files"]:
        path = ROOT / entry["path"]
        assert path.is_file(), f"listed evidence version missing: {entry['path']}"
        assert _sha256(path) == entry["sha256"], f"evidence bytes changed in place: {entry['path']}"


def test_every_devnet_evidence_file_is_listed() -> None:
    listed = {(e["path"], e["sha256"]) for e in _versions()["files"]}
    for path in sorted((EVIDENCE / "devnet").rglob("*.json")):
        rel = path.relative_to(ROOT).as_posix()
        assert (rel, _sha256(path)) in listed, (
            f"{rel} is not listed in evidence-versions.json with its current hash; "
            "publish a correction as a new file and append a CHANGELOG entry instead of editing in place"
        )


def test_changelog_mentions_every_edited_file() -> None:
    changelog = (EVIDENCE / "CHANGELOG.md").read_text(encoding="utf-8")
    for entry in _versions()["files"]:
        if entry["status"] == "current-edited-in-place":
            assert entry["changelog"] in changelog
            assert entry["sha256"] in changelog
            assert entry["supersedes_sha256"] in changelog
