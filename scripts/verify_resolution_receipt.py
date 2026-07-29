#!/usr/bin/env python3
"""Verify a Ward resolution receipt without running the resolution engine.

This script is the reviewer-facing verification path. It validates the public
receipt shape, recomputes the canonical receipt hash, checks the derived receipt
ID, and enforces the unsigned/no-secret boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_FORBIDDEN_KEY_RE = re.compile(
    r"(^|_)(private|secret|mnemonic|seed|password|passphrase|api_key|token|signature|signingpubkey)($|_)",
    re.IGNORECASE,
)


def _freeze_json(value: Any, path: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return frozen
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    normalized = _freeze_json(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _walk_keys(value: Any, path: str = "receipt") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _FORBIDDEN_KEY_RE.search(key):
                hits.append(f"{path}.{key}")
            hits.extend(_walk_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_walk_keys(item, f"{path}[{index}]"))
    return hits


def _validate_schema(receipt: Any, schema_path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:
        raise RuntimeError("jsonschema is required for schema validation") from exc

    schema = _load_json(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(receipt), key=lambda item: list(item.path)
    )
    if errors:
        rendered = "; ".join(
            f"/{'/'.join(map(str, error.path))}: {error.message}" for error in errors[:5]
        )
        raise ValueError(f"schema validation failed: {rendered}")


def verify_receipt(receipt_path: Path, schema_path: Path) -> dict[str, Any]:
    receipt = _load_json(receipt_path)
    if not isinstance(receipt, dict):
        raise ValueError("receipt JSON must be an object")

    _validate_schema(receipt, schema_path)

    stored_hash = receipt.get("receipt_hash")
    stored_id = receipt.get("receipt_id")
    payload = dict(receipt)
    payload.pop("receipt_id", None)
    payload.pop("receipt_hash", None)
    computed_hash = canonical_hash(payload)

    if stored_hash != computed_hash:
        raise ValueError(f"receipt_hash mismatch: stored={stored_hash} computed={computed_hash}")
    expected_id = f"wr_{computed_hash[:24]}"
    if stored_id != expected_id:
        raise ValueError(f"receipt_id mismatch: stored={stored_id} expected={expected_id}")
    if receipt.get("ward_signed") is not False:
        raise ValueError("ward_signed must be false")
    for index, action in enumerate(receipt.get("unsigned_actions", [])):
        if action.get("ward_signed") is not False:
            raise ValueError(f"unsigned_actions[{index}].ward_signed must be false")

    forbidden = _walk_keys(receipt)
    if forbidden:
        raise ValueError("secret-like receipt key(s) found: " + ", ".join(forbidden[:8]))

    return {
        "ok": True,
        "receipt": str(receipt_path),
        "schema": str(schema_path),
        "receipt_id": stored_id,
        "receipt_hash": stored_hash,
        "hash_matches": True,
        "ward_signed": False,
        "decision": receipt.get("decision"),
        "workflow_type": receipt.get("case", {}).get("workflow_type"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, help="Receipt JSON to verify")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schemas/ward-resolution-receipt-v1.schema.json"),
        help="Ward receipt JSON schema",
    )
    args = parser.parse_args()

    try:
        result = verify_receipt(args.receipt, args.schema)
    except Exception as exc:  # noqa: BLE001 - CLI renders reviewer-facing failure.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
