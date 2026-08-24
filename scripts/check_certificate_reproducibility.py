#!/usr/bin/env python3
"""Re-query pinned ledgers for issued Ward evidence certificates."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = REPO_ROOT / "docs/security/evidence/certificate-index.json"
DEFAULT_STATUS = (
    REPO_ROOT / "docs/security/evidence/certificate-reproducibility-status.json"
)


def query_ledger(
    rpc_url: str, ledger_index: int, timeout: float = 20.0
) -> dict[str, Any]:
    payload = {
        "method": "ledger",
        "params": [
            {
                "ledger_index": ledger_index,
                "transactions": False,
                "expand": False,
            }
        ],
    }
    request = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    if not isinstance(decoded, dict):
        raise ValueError("XRPL RPC response must be a JSON object")
    return decoded


def _is_ledger_not_found(result: dict[str, Any]) -> bool:
    code = str(result.get("error", "")).lower()
    message = " ".join(
        str(result.get(field, ""))
        for field in ("error_message", "error_exception", "message")
    ).lower()
    return code in {"lgrnotfound", "ledgernotfound"} or (
        "ledger" in message and "not found" in message
    )


def check_certificate(
    certificate: dict[str, Any],
    *,
    query: Callable[[str, int], dict[str, Any]] = query_ledger,
) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    certificate_id = str(certificate.get("certificate_id", ""))
    network = certificate.get("network", {})
    rpc_url = str(network.get("rpc_url", ""))
    ledger_index = network.get("ledger_index")
    base = {
        "certificate_id": certificate_id,
        "artifact": certificate.get("artifact"),
        "network": network.get("name"),
        "rpc_url": rpc_url,
        "ledger_index": ledger_index,
        "checked_at": checked_at,
    }

    if not rpc_url or not isinstance(ledger_index, int):
        return {
            **base,
            "status": "check_error",
            "error_code": "invalid_index_entry",
            "detail": "Certificate index entry requires rpc_url and integer ledger_index.",
        }

    try:
        response = query(rpc_url, ledger_index)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {
            **base,
            "status": "check_error",
            "error_code": type(exc).__name__,
            "detail": str(exc),
        }

    result = response.get("result")
    if not isinstance(result, dict):
        return {
            **base,
            "status": "check_error",
            "error_code": "malformed_rpc_response",
            "detail": "XRPL RPC response did not contain an object result.",
        }
    if _is_ledger_not_found(result):
        return {
            **base,
            "status": "unreproducible",
            "error_code": str(result.get("error", "lgrNotFound")),
            "detail": "Pinned ledger is no longer available from the public RPC endpoint.",
        }
    if result.get("error"):
        return {
            **base,
            "status": "check_error",
            "error_code": str(result.get("error")),
            "detail": str(result.get("error_message") or "XRPL RPC returned an error."),
        }

    ledger = result.get("ledger")
    returned_index = result.get("ledger_index")
    if isinstance(ledger, dict):
        returned_index = ledger.get("ledger_index", returned_index)
    try:
        returned_index = int(returned_index)
    except (TypeError, ValueError):
        returned_index = None
    if returned_index != ledger_index:
        return {
            **base,
            "status": "check_error",
            "error_code": "ledger_index_mismatch",
            "detail": f"RPC returned ledger_index={returned_index!r}.",
        }

    return {
        **base,
        "status": "reproducible",
        "error_code": None,
        "detail": "Pinned ledger remains available from the public RPC endpoint.",
    }


def check_index(
    index: dict[str, Any],
    *,
    query: Callable[[str, int], dict[str, Any]] = query_ledger,
) -> dict[str, Any]:
    certificates = index.get("certificates")
    if not isinstance(certificates, list):
        raise ValueError("certificate index must contain a certificates list")
    results = [check_certificate(item, query=query) for item in certificates]
    return {
        "schema": "ward-certificate-reproducibility-status/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_index": "docs/security/evidence/certificate-index.json",
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
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--fail-on-unreproducible", action="store_true")
    parser.add_argument("--fail-on-check-error", action="store_true")
    args = parser.parse_args()

    try:
        index = json.loads(args.index.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError("certificate index must be a JSON object")
        status = check_index(index)
    except Exception as exc:  # noqa: BLE001 - scheduled CLI needs a clear failure
        print(
            f"ERROR: certificate reproducibility check failed: {exc}", file=sys.stderr
        )
        return 2

    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    for certificate in status["certificates"]:
        print(
            f"{certificate['certificate_id']}: {certificate['status']} "
            f"(ledger {certificate['ledger_index']}) - {certificate['detail']}"
        )

    if args.fail_on_check_error and status["summary"]["check_error"]:
        return 2
    if args.fail_on_unreproducible and status["summary"]["unreproducible"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
