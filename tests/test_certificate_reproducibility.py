from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_certificate_reproducibility import (
    assert_issuance_has_archive,
    check_certificate,
    check_index,
    index_certificate,
)
from ward.conformance_rules import COVENANT_RULE_SET_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_FIXTURE = "tests/fixtures/certificates/minimal-raw-reads.json"


def _gate_a_pins(certificate: dict) -> dict:
    """Stamp Gate A pins required for NEW index_certificate entries."""
    certificate = dict(certificate)
    certificate["resolver_commit_sha"] = "c" * 40
    certificate["covenant_rule_set_version"] = COVENANT_RULE_SET_VERSION
    return certificate


def _legacy_certificate() -> dict:
    return {
        "certificate_id": "KV-IV-2026-0712-001",
        "artifact": "docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md",
        "legacy": True,
        "reproducibility_label": "unreproducible/legacy",
        "raw_reads_archive": None,
        "network": {
            "name": "XRPL Devnet",
            "rpc_url": "https://s.devnet.rippletest.net:51234",
            "ledger_index": 3_576_434,
        },
        "transactions": [
            {
                "step": "VaultCreate",
                "hash": "8109F9AF2F6425FCF71AFA6A8001B5B71BB95FB72671D1ED60DED92EA43EC5B8",
            }
        ],
    }


def _archived_certificate(repo_path: str, sha256: str | None = None) -> dict:
    pointer: dict = {
        "schema": "ward-raw-ledger-reads/v1",
        "repo_path": repo_path,
        "complete": True,
        "r2_binding": "EVIDENCE_ARCHIVE",
        "r2_bucket": "ward-ledger-evidence",
        "r2_key": "certificates/xrpl-devnet/11/evidence.raw-reads.json",
    }
    if sha256:
        pointer["sha256"] = sha256
    return {
        "certificate_id": "TEST-ARCHIVED-001",
        "artifact": "docs/security/evidence/archives/evidence.json",
        "legacy": False,
        "raw_reads_archive": pointer,
        "network": {
            "name": "XRPL Devnet",
            "rpc_url": "https://s.devnet.rippletest.net:51234",
            "ledger_index": 11,
        },
        "transactions": [{"step": "VaultCreate", "hash": "A" * 64}],
    }


def _complete_archive(tx_hash: str = "A" * 64) -> dict:
    return {
        "schema": "ward-raw-ledger-reads/v1",
        "network": {"name": "XRPL Devnet", "ledger_index": 11},
        "completeness": {"complete": True, "errors": []},
        "reads": [
            {
                "source": "lifecycle.tx_results.VaultCreate.raw",
                "request": {"transaction_hash": tx_hash},
                "response": {"ledger_index": 11, "hash": tx_hash},
            }
        ],
    }


def test_legacy_cert_is_unreproducible_without_fabricating_archive() -> None:
    queried = []

    def forbidden_rpc(url, ledger_index):
        queried.append((url, ledger_index))
        return {"result": {"ledger": {"ledger_index": ledger_index}}}

    status = check_index(
        {"certificates": [_legacy_certificate()]},
        query=forbidden_rpc,
    )

    assert queried == []
    assert status["summary"] == {
        "total": 1,
        "reproducible": 0,
        "unreproducible": 1,
        "check_error": 0,
    }
    result = status["certificates"][0]
    assert result["status"] == "unreproducible"
    assert result["legacy"] is True
    assert result["reproducibility_label"] == "unreproducible/legacy"
    assert result["error_code"] == "missing_raw_reads_archive"
    assert result["raw_reads_archive"] is None
    assert result["proof_source"] == "raw_reads_archive"
    assert "KV-IV-2026-0712-001" in result["detail"]
    assert "Do not fabricate" in result["detail"]


def test_weekly_checker_reproves_from_archive_and_skips_public_rpc(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "evidence.raw-reads.json"
    archive = _complete_archive()
    archive_path.write_text(__import__("json").dumps(archive), encoding="utf-8")
    queried = []

    def forbidden_rpc(url, ledger_index):
        queried.append((url, ledger_index))
        raise AssertionError("weekly proof must not query public RPC")

    def load_archive(_certificate):
        return archive

    status = check_index(
        {"certificates": [_archived_certificate(str(archive_path))]},
        load_archive=load_archive,
        query=forbidden_rpc,
    )

    assert queried == []
    assert status["summary"]["reproducible"] == 1
    assert status["certificates"][0]["status"] == "reproducible"
    assert status["certificates"][0]["proof_source"] == "raw_reads_archive"
    assert "Public Devnet RPC was not queried" in status["certificates"][0]["detail"]


def test_missing_archive_does_not_silently_pass() -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("public RPC must not be used as a fallback")

    result = check_certificate(
        _archived_certificate("docs/security/evidence/archives/missing.raw-reads.json"),
        load_archive=lambda _cert: (_ for _ in ()).throw(FileNotFoundError("missing")),
        query=boom,
    )
    assert result["status"] == "unreproducible"
    assert result["error_code"] == "missing_raw_reads_archive"


def test_lgr_not_found_in_archive_does_not_silently_pass() -> None:
    def load_archive(_certificate):
        return {
            "schema": "ward-raw-ledger-reads/v1",
            "network": {"ledger_index": 11},
            "completeness": {"complete": True, "errors": []},
            "reads": [
                {
                    "source": "ledger",
                    "request": {"ledger_index": 11},
                    "response": {
                        "result": {
                            "error": "lgrNotFound",
                            "error_message": "ledgerNotFound",
                        }
                    },
                }
            ],
        }

    result = check_certificate(
        _archived_certificate("unused.json"),
        load_archive=load_archive,
    )
    assert result["status"] == "unreproducible"
    assert result["error_code"] == "lgrNotFound"


def test_incomplete_archive_does_not_silently_pass() -> None:
    def load_archive(_certificate):
        return {
            "schema": "ward-raw-ledger-reads/v1",
            "completeness": {"complete": False, "errors": ["missing tx"]},
            "reads": [],
        }

    result = check_certificate(
        _archived_certificate("unused.json"),
        load_archive=load_archive,
    )
    assert result["status"] == "unreproducible"
    assert result["error_code"] == "incomplete_raw_reads_archive"


def test_transient_loader_failure_is_not_mislabeled_unreproducible() -> None:
    def load_archive(_certificate):
        raise OSError("temporary read failure")

    result = check_certificate(
        _archived_certificate("unused.json"),
        load_archive=load_archive,
    )
    assert result["status"] == "check_error"
    assert result["error_code"] == "OSError"


def test_issuance_refuses_certificates_without_an_archive() -> None:
    with pytest.raises(ValueError, match="archive-on-issuance"):
        assert_issuance_has_archive(
            {
                "certificate_id": "NEW-CERT",
                "network": {"name": "XRPL Devnet", "ledger_index": 1},
            }
        )


def test_legacy_pre_archive_certificates_may_omit_raw_reads() -> None:
    assert_issuance_has_archive(
        {
            "certificate_id": "KV-IV-2026-0712-001",
            "legacy_pre_archive": True,
        }
    )


def test_legacy_flag_certificates_may_omit_raw_reads() -> None:
    assert_issuance_has_archive(
        {
            "certificate_id": "KV-IV-2026-0712-001",
            "legacy": True,
        }
    )


def test_index_refuses_certificates_without_an_archive() -> None:
    with pytest.raises(ValueError, match="archive-on-issuance"):
        index_certificate({"certificates": []}, {"certificate_id": "NEW-CERT"})


def test_index_accepts_certificate_with_replayable_archive() -> None:
    indexed = index_certificate(
        {"certificates": []},
        _gate_a_pins(
            {
                "certificate_id": "WARD-DEVNET-ARCHIVE-FIXTURE",
                "raw_reads_archive": ARCHIVE_FIXTURE,
                "network": {
                    "name": "XRPL Devnet",
                    "ledger_index": 4_740_522,
                },
            }
        ),
        repo_root=REPO_ROOT,
    )
    assert indexed["certificates"][0]["certificate_id"] == "WARD-DEVNET-ARCHIVE-FIXTURE"


def test_index_accepts_dict_archive_pointer() -> None:
    indexed = index_certificate(
        {"certificates": []},
        _gate_a_pins(
            {
                "certificate_id": "WARD-DEVNET-ARCHIVE-FIXTURE-DICT",
                "raw_reads_archive": {
                    "repo_path": ARCHIVE_FIXTURE,
                    "complete": True,
                },
                "network": {
                    "name": "XRPL Devnet",
                    "ledger_index": 4_740_522,
                },
            }
        ),
        repo_root=REPO_ROOT,
    )
    assert (
        indexed["certificates"][0]["certificate_id"]
        == "WARD-DEVNET-ARCHIVE-FIXTURE-DICT"
    )


def test_index_refuses_new_certs_without_gate_a_pins() -> None:
    with pytest.raises(ValueError, match="resolver_commit_sha"):
        index_certificate(
            {"certificates": []},
            {
                "certificate_id": "NEW-NO-PINS",
                "raw_reads_archive": ARCHIVE_FIXTURE,
                "network": {
                    "name": "XRPL Devnet",
                    "ledger_index": 4_740_522,
                },
            },
            repo_root=REPO_ROOT,
        )


def test_cli_fail_on_unreproducible_ignores_disclosed_legacy_only(tmp_path, monkeypatch) -> None:
    """The permanent legacy KV entry must not mask a regressed archive."""
    import json
    import shutil
    import sys

    from scripts import check_certificate_reproducibility as cli

    index = json.loads((REPO_ROOT / "docs/security/evidence/certificate-index.json").read_text())
    status_path = tmp_path / "status.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["check", "--status", str(status_path), "--fail-on-unreproducible", "--fail-on-check-error"],
    )
    assert cli.main() == 0
    status = json.loads(status_path.read_text())
    by_id = {c["certificate_id"]: c for c in status["certificates"]}
    assert by_id["KV-IV-2026-0712-001"]["status"] == "unreproducible"
    assert by_id["KV-IV-2026-0712-001"]["legacy"] is True
    assert by_id["WARD-DEVNET-20260901-001"]["status"] == "reproducible"
    assert by_id["WARD-DEVNET-20260902-001"]["status"] == "reproducible"

    # Tamper with one archive copy: the pinned sha256 no longer matches.
    fake_root = tmp_path / "repo"
    archives = fake_root / "docs/security/evidence/archives"
    shutil.copytree(REPO_ROOT / "docs/security/evidence/archives", archives)
    target = archives / "ward-evidence-pre-resolution-2026-09-01.raw-reads.json"
    target.write_bytes(target.read_bytes().replace(b"}", b" }", 1))
    monkeypatch.setattr(cli, "REPO_ROOT", fake_root)
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check",
            "--index",
            str(index_path),
            "--status",
            str(status_path),
            "--fail-on-unreproducible",
        ],
    )
    assert cli.main() == 1
    status = json.loads(status_path.read_text())
    by_id = {c["certificate_id"]: c for c in status["certificates"]}
    assert by_id["WARD-DEVNET-20260901-001"]["error_code"] == "archive_sha256_mismatch"
