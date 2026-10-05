#!/usr/bin/env python3
"""Re-prove issued Ward evidence certificates from archived raw ledger reads.

Weekly verification must not re-query public Devnet RPC. Pinned ledgers expire
(lgrNotFound). Proof is reconstructed only from the raw-read archive persisted
at issuance into the repo store (docs/security/evidence/archives) and/or the
EVIDENCE_ARCHIVE R2 binding (bucket ward-ledger-evidence). Missing archives
fail closed as unreproducible. Legacy certificates with raw_reads_archive null
are labeled unreproducible/legacy and must not be given a fabricated archive.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = REPO_ROOT / "docs/security/evidence/certificate-index.json"
DEFAULT_STATUS = (
    REPO_ROOT / "docs/security/evidence/certificate-reproducibility-status.json"
)
DEFAULT_ARCHIVE_STORE = REPO_ROOT / "docs/security/evidence/archives"
RAW_READS_SCHEMA = "ward-raw-ledger-reads/v1"
EVIDENCE_ARCHIVE_BINDING = "EVIDENCE_ARCHIVE"
EVIDENCE_ARCHIVE_BUCKET = "ward-ledger-evidence"


def _is_ledger_not_found(result: dict[str, Any]) -> bool:
    code = str(result.get("error", "")).lower()
    message = " ".join(
        str(result.get(field, ""))
        for field in ("error_message", "error_exception", "message")
    ).lower()
    return code in {"lgrnotfound", "ledgernotfound"} or (
        "ledger" in message and "not found" in message
    )


def _walk_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            found.extend(_walk_strings(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_strings(child))
    return found


def _is_missing_archive_ref(ref: Any) -> bool:
    return ref in (None, "", {}, [])


def _archive_pointer_path(ref: Any) -> str | None:
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    if isinstance(ref, dict):
        relative = ref.get("repo_path") or ref.get("path") or ref.get("file") or ""
        if relative:
            return str(relative)
    return None


def resolve_archive_path(
    certificate: dict[str, Any], *, repo_root: Path = REPO_ROOT
) -> Path | None:
    """Return the repo-store path for a certificate archive, or None if absent."""
    relative = _archive_pointer_path(certificate.get("raw_reads_archive"))
    if not relative:
        return None
    path = Path(str(relative))
    if not path.is_absolute():
        path = repo_root / path
    return path


def default_load_archive(
    certificate: dict[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any] | None:
    path = resolve_archive_path(certificate, repo_root=repo_root)
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("raw-read archive must be a JSON object")
    return loaded


def _is_legacy_certificate(certificate: dict[str, Any]) -> bool:
    if certificate.get("legacy") is True:
        return True
    if certificate.get("legacy_pre_archive") is True:
        return True
    label = str(certificate.get("reproducibility_label", "")).lower()
    return "legacy" in label


def _legacy_unreproducible(certificate: dict[str, Any]) -> bool:
    if _is_legacy_certificate(certificate):
        return True
    return _is_missing_archive_ref(certificate.get("raw_reads_archive"))


def prove_from_archive(
    certificate: dict[str, Any], archive: dict[str, Any]
) -> dict[str, Any]:
    """Re-prove certificate claims from archived reads. Never uses public RPC."""
    errors: list[str] = []
    if archive.get("schema") != RAW_READS_SCHEMA:
        errors.append(
            f'archive schema must be "{RAW_READS_SCHEMA}", '
            f"got {archive.get('schema')!r}"
        )

    reads = archive.get("reads")
    if not isinstance(reads, list) or not reads:
        errors.append("raw-read archive reads must be a non-empty list")
        reads = []

    completeness = archive.get("completeness")
    if not isinstance(completeness, dict) or completeness.get("complete") is not True:
        errors.append("raw-read archive completeness.complete must be true")
    elif completeness.get("errors"):
        errors.append("raw-read archive completeness.errors must be empty")

    for index, read in enumerate(reads):
        if not isinstance(read, dict):
            errors.append(f"reads[{index}] must be an object")
            continue
        response = read.get("response")
        payload = response
        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            payload = response["result"]
        if isinstance(payload, dict) and _is_ledger_not_found(payload):
            return {
                "ok": False,
                "status": "unreproducible",
                "error_code": str(payload.get("error", "lgrNotFound")),
                "detail": (
                    "Archived raw read contains lgrNotFound; public RPC is not "
                    "consulted and this does not silently pass."
                ),
            }
        if not isinstance(read.get("request"), dict):
            errors.append(f"reads[{index}].request must be an object")
        if "response" not in read and "error" not in read:
            errors.append(f"reads[{index}] must contain response or error")

    blob_parts = _walk_strings(archive)
    blob = " ".join(blob_parts)
    missing_hashes: list[str] = []
    for transaction in certificate.get("transactions") or []:
        if not isinstance(transaction, dict):
            continue
        tx_hash = transaction.get("hash")
        if isinstance(tx_hash, str) and tx_hash and tx_hash not in blob:
            missing_hashes.append(tx_hash)
    if missing_hashes:
        errors.append(
            "archived reads do not contain certificate transaction hashes: "
            + ", ".join(missing_hashes)
        )

    expected_ledger = (certificate.get("network") or {}).get("ledger_index")
    archived_ledger = (archive.get("network") or {}).get("ledger_index")
    if expected_ledger is not None and archived_ledger is not None:
        try:
            if int(archived_ledger) != int(expected_ledger):
                errors.append(
                    f"archive ledger_index {archived_ledger!r} does not match "
                    f"certificate ledger_index {expected_ledger!r}"
                )
        except (TypeError, ValueError):
            errors.append("archive network.ledger_index is not an integer")

    if errors:
        return {
            "ok": False,
            "status": "unreproducible",
            "error_code": "incomplete_raw_reads_archive",
            "detail": "; ".join(errors),
        }
    return {
        "ok": True,
        "status": "reproducible",
        "error_code": None,
        "detail": (
            "Re-proved from archived raw ledger reads "
            f"({EVIDENCE_ARCHIVE_BINDING}/{EVIDENCE_ARCHIVE_BUCKET} and/or "
            "docs/security/evidence/archives). Public Devnet RPC was not queried."
        ),
    }


def replay_from_archive(
    certificate: dict[str, Any],
    archive: dict[str, Any],
) -> dict[str, Any]:
    """Issuance/index helper: validate archive structure. Not a weekly RPC path."""
    schema = archive.get("schema")
    if schema != RAW_READS_SCHEMA:
        raise ValueError(
            f"raw-reads archive schema must be {RAW_READS_SCHEMA}, got {schema!r}"
        )
    reads = archive.get("reads")
    if not isinstance(reads, list) or not reads:
        raise ValueError("raw-reads archive requires a non-empty reads list")
    for index, read in enumerate(reads):
        if not isinstance(read, dict):
            raise ValueError(f"raw-reads archive reads[{index}] must be an object")
        if not isinstance(read.get("request"), dict) or not isinstance(
            read.get("response"), dict
        ):
            raise ValueError(
                f"raw-reads archive reads[{index}] requires request and response objects"
            )

    network = certificate.get("network", {})
    ledger_index = network.get("ledger_index") if isinstance(network, dict) else None
    archive_network = archive.get("network", {})
    archive_index = (
        archive_network.get("ledger_index")
        if isinstance(archive_network, dict)
        else None
    )
    if ledger_index != archive_index:
        raise ValueError(
            f"archived ledger_index {archive_index!r} does not match certificate "
            f"ledger_index {ledger_index!r}"
        )
    return archive


def assert_issuance_has_archive(certificate: dict[str, Any]) -> None:
    """Refuse new certificates that were not issued with a raw-reads archive."""
    if _is_legacy_certificate(certificate):
        return
    if _archive_pointer_path(certificate.get("raw_reads_archive")) is None:
        raise ValueError(
            "archive-on-issuance requires raw_reads_archive; "
            "legacy certificates must set legacy_pre_archive true"
        )


def index_certificate(
    index: dict[str, Any],
    certificate: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Refuse to add a certificate that was not issued with a raw-reads archive."""
    assert_issuance_has_archive(certificate)
    if not _is_legacy_certificate(certificate):
        # Gate A: NEW indexed certs must carry resolver/ruleset pins.
        # Grandfathered indexed certs already missing pins are not rewritten.
        from ward.certificate_pins import require_new_certificate_pins

        require_new_certificate_pins(certificate)
        archive_path = resolve_archive_path(certificate, repo_root=repo_root)
        if archive_path is None or not archive_path.is_file():
            raise FileNotFoundError(
                f"refusing to index {certificate.get('certificate_id')!r}: "
                f"raw_reads_archive not found: {archive_path}"
            )
        archive = default_load_archive(certificate, repo_root=repo_root)
        if archive is None:
            raise FileNotFoundError(
                f"refusing to index {certificate.get('certificate_id')!r}: "
                "raw_reads_archive could not be loaded"
            )
        replay_from_archive(certificate, archive)
    certificates = index.setdefault("certificates", [])
    if not isinstance(certificates, list):
        raise ValueError("certificate index must contain a certificates list")
    cert_id = certificate.get("certificate_id")
    if any(item.get("certificate_id") == cert_id for item in certificates):
        raise ValueError(f"certificate_id already indexed: {cert_id}")
    certificates.append(certificate)
    return index


def check_certificate(
    certificate: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    load_archive: Callable[..., dict[str, Any] | None] | None = None,
    query: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Check one certificate. `query` is accepted but never used."""
    del query  # public RPC must not be the weekly proof source
    checked_at = datetime.now(timezone.utc).isoformat()
    certificate_id = str(certificate.get("certificate_id", ""))
    network = certificate.get("network", {})
    rpc_url = str(network.get("rpc_url", ""))
    ledger_index = network.get("ledger_index")
    archive_ref = certificate.get("raw_reads_archive")
    legacy = _legacy_unreproducible(certificate)
    base = {
        "certificate_id": certificate_id,
        "artifact": certificate.get("artifact"),
        "network": network.get("name"),
        "rpc_url": rpc_url,
        "ledger_index": ledger_index,
        "checked_at": checked_at,
        "proof_source": "raw_reads_archive",
        "raw_reads_archive": archive_ref
        if not _is_missing_archive_ref(archive_ref)
        else None,
        "legacy": legacy,
        "reproducibility_label": (
            "unreproducible/legacy"
            if legacy and _is_missing_archive_ref(archive_ref)
            else None
        ),
        "archive_binding": EVIDENCE_ARCHIVE_BINDING,
        "archive_bucket": EVIDENCE_ARCHIVE_BUCKET,
    }

    if _is_missing_archive_ref(archive_ref):
        label = "unreproducible/legacy" if legacy else "unreproducible"
        detail = (
            f"Certificate {certificate_id or '(missing id)'} has raw_reads_archive "
            "null. Weekly re-proof uses the issuance archive store, not public "
            "Devnet RPC (which expires with lgrNotFound). No archive is fabricated."
        )
        if certificate_id == "KV-IV-2026-0712-001":
            detail = (
                "Legacy certificate KV-IV-2026-0712-001: raw_reads_archive is null. "
                "XRPL Devnet ledger 3576434 is unreproducible (public RPC returns "
                "lgrNotFound; no issuance archive exists). Labeled "
                "unreproducible/legacy. Do not fabricate an archive."
            )
        return {
            **base,
            "status": "unreproducible",
            "error_code": "missing_raw_reads_archive",
            "reproducibility_label": label,
            "detail": detail,
        }

    loader = load_archive or (
        lambda cert, repo_root=repo_root: default_load_archive(
            cert, repo_root=repo_root
        )
    )
    try:
        archive = loader(certificate)
    except FileNotFoundError as exc:
        return {
            **base,
            "status": "unreproducible",
            "error_code": "missing_raw_reads_archive",
            "detail": (
                f"Indexed raw-read archive is missing on disk ({exc}). "
                "Failing closed; public RPC is not queried."
            ),
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            **base,
            "status": "check_error",
            "error_code": type(exc).__name__,
            "detail": f"Could not load raw-read archive: {exc}",
        }

    if archive is None:
        return {
            **base,
            "status": "unreproducible",
            "error_code": "missing_raw_reads_archive",
            "detail": (
                "Archive loader returned no raw reads. Failing closed; "
                "public RPC is not queried."
            ),
        }

    if isinstance(archive_ref, dict) and isinstance(archive_ref.get("sha256"), str):
        path = resolve_archive_path(certificate, repo_root=repo_root)
        if path is not None and path.is_file():
            import hashlib

            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != archive_ref["sha256"]:
                return {
                    **base,
                    "status": "unreproducible",
                    "error_code": "archive_sha256_mismatch",
                    "detail": "On-disk raw-read archive SHA-256 does not match the index.",
                }

    proof = prove_from_archive(certificate, archive)
    return {
        **base,
        "status": proof["status"],
        "error_code": proof["error_code"],
        "reproducibility_label": (
            "reproducible" if proof["ok"] else base["reproducibility_label"]
        ),
        "detail": proof["detail"],
    }


def check_index(
    index: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    load_archive: Callable[..., dict[str, Any] | None] | None = None,
    query: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    del query
    certificates = index.get("certificates")
    if not isinstance(certificates, list):
        raise ValueError("certificate index must contain a certificates list")
    results = [
        check_certificate(item, repo_root=repo_root, load_archive=load_archive)
        for item in certificates
    ]
    return {
        "schema": "ward-certificate-reproducibility-status/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_index": "docs/security/evidence/certificate-index.json",
        "proof_source": "raw_reads_archive",
        "archive_binding": EVIDENCE_ARCHIVE_BINDING,
        "archive_bucket": EVIDENCE_ARCHIVE_BUCKET,
        "summary": {
            "total": len(results),
            "reproducible": sum(item["status"] == "reproducible" for item in results),
            "unreproducible": sum(
                item["status"] == "unreproducible" for item in results
            ),
            "check_error": sum(item["status"] == "check_error" for item in results),
        },
        "certificates": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--status",
        type=Path,
        default=DEFAULT_STATUS,
        help=(
            "Where to write the status JSON. Defaults to the committed repo file "
            "(used by the weekly workflow). Reviewers should pass a scratch path, "
            "e.g. --status /tmp/ward-certificate-status.json."
        ),
    )
    parser.add_argument("--fail-on-unreproducible", action="store_true")
    parser.add_argument("--fail-on-check-error", action="store_true")
    args = parser.parse_args()

    try:
        index = json.loads(args.index.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError("certificate index must be a JSON object")
        status = check_index(index, repo_root=REPO_ROOT)
    except Exception as exc:  # noqa: BLE001 - scheduled CLI needs a clear failure
        print(
            f"ERROR: certificate reproducibility check failed: {exc}", file=sys.stderr
        )
        return 2

    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    for certificate in status["certificates"]:
        label = certificate.get("reproducibility_label") or certificate["status"]
        print(
            f"{certificate['certificate_id']}: {label} "
            f"(ledger {certificate['ledger_index']}) - {certificate['detail']}"
        )

    if args.fail_on_check_error and status["summary"]["check_error"]:
        return 2
    # Legacy pre-archive certificates (e.g. KV-IV-2026-0712-001) are disclosed
    # as unreproducible/legacy and can never re-prove. Count only certificates
    # that were issued with an archive, so a tampered or missing archive is a
    # visible failure instead of being masked by the permanent legacy entry.
    regressed = [
        c["certificate_id"]
        for c in status["certificates"]
        if c.get("status") == "unreproducible" and not c.get("legacy")
    ]
    if args.fail_on_unreproducible and regressed:
        print(f"UNREPRODUCIBLE (non-legacy): {', '.join(regressed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
