#!/usr/bin/env python3
"""Validate a Ward design-partner evidence bundle.

This is an offline structural gate. It does not query XRPL and it does not
prove a ledger state by itself. Its job is to reject evidence bundles that are
not reproducible, contain secrets, use simulated language, or blur the
`ward_signed = False` boundary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL = {
    "protocol",
    "evidence_type",
    "generated_at",
    "commit",
    "network",
    "source",
    "objects",
    "transactions",
    "ward_result",
}

REQUIRED_OBJECTS = {
    "vault_id",
    "loan_broker_id",
    "loan_id",
    "policy_nft_id",
    "pool_address",
    "claimant_address",
    "defaulted_vault",
}

REQUIRED_WARD_RESULT = {
    "ward_signed",
    "approved",
    "steps_passed",
    "checks",
    "rejection_reason",
    "settlement",
}

FORBIDDEN_KEY_PATTERN = re.compile(
    r"(seed|secret|private[_-]?key|wallet[_-]?seed|mnemonic|passphrase)",
    re.IGNORECASE,
)
FORBIDDEN_VALUE_PATTERN = re.compile(
    r"\b(simulated|simulation|mock|fake|placeholder|dummy)\b",
    re.IGNORECASE,
)


def _walk(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    nodes = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            nodes.extend(_walk(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nodes.extend(_walk(child, f"{path}[{index}]"))
    return nodes


def _missing(required: set[str], actual: dict[str, Any]) -> list[str]:
    return sorted(required - set(actual))


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing_top = _missing(REQUIRED_TOP_LEVEL, bundle)
    if missing_top:
        errors.append(f"missing top-level fields: {', '.join(missing_top)}")

    if bundle.get("protocol") != "Ward Protocol":
        errors.append('protocol must be "Ward Protocol"')

    if bundle.get("evidence_type") != "xrpl-devnet-lifecycle":
        errors.append('evidence_type must be "xrpl-devnet-lifecycle"')

    network = bundle.get("network")
    if not isinstance(network, dict):
        errors.append("network must be an object")
    else:
        if network.get("name") != "XRPL Devnet":
            errors.append('network.name must be "XRPL Devnet"')
        if not network.get("ledger_index"):
            errors.append("network.ledger_index is required")

    objects = bundle.get("objects")
    if not isinstance(objects, dict):
        errors.append("objects must be an object")
    else:
        missing_objects = _missing(REQUIRED_OBJECTS, objects)
        if missing_objects:
            errors.append(f"missing object identifiers: {', '.join(missing_objects)}")

    transactions = bundle.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        errors.append("transactions must be a non-empty list")
    else:
        for index, tx in enumerate(transactions):
            if not isinstance(tx, dict):
                errors.append(f"transactions[{index}] must be an object")
                continue
            for field in ("hash", "type", "ledger_index"):
                if not tx.get(field):
                    errors.append(f"transactions[{index}].{field} is required")

    ward_result = bundle.get("ward_result")
    if not isinstance(ward_result, dict):
        errors.append("ward_result must be an object")
    else:
        missing_result = _missing(REQUIRED_WARD_RESULT, ward_result)
        if missing_result:
            errors.append(f"missing ward_result fields: {', '.join(missing_result)}")
        if ward_result.get("ward_signed") is not False:
            errors.append("ward_result.ward_signed must be false")
        if not isinstance(ward_result.get("steps_passed"), int):
            errors.append("ward_result.steps_passed must be an integer")
        settlement = ward_result.get("settlement")
        if not isinstance(settlement, dict):
            errors.append("ward_result.settlement must be an object")
        elif settlement.get("signed_by_ward") is not False:
            errors.append("ward_result.settlement.signed_by_ward must be false")

        checks = ward_result.get("checks")
        if not isinstance(checks, list):
            errors.append("ward_result.checks must be a list")
        else:
            numbers = set()
            for index, check in enumerate(checks):
                if not isinstance(check, dict):
                    errors.append(f"ward_result.checks[{index}] must be an object")
                    continue
                number = check.get("number")
                numbers.add(number)
                if not isinstance(number, int):
                    errors.append(f"ward_result.checks[{index}].number must be an integer")
                if check.get("status") not in {"passed", "failed", "not_applicable"}:
                    errors.append(
                        f"ward_result.checks[{index}].status must be passed, failed, or not_applicable"
                    )
            expected_numbers = set(range(1, 10))
            if numbers != expected_numbers:
                errors.append("ward_result.checks must contain exactly steps 1 through 9")

    for path, value in _walk(bundle):
        if FORBIDDEN_KEY_PATTERN.search(path):
            errors.append(f"secret-like field is forbidden: {path}")
        if isinstance(value, str) and FORBIDDEN_VALUE_PATTERN.search(value):
            errors.append(f"simulated or placeholder language is forbidden at {path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Path to evidence JSON")
    args = parser.parse_args()

    try:
        data = json.loads(args.bundle.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - CLI should return a useful error
        print(f"ERROR: could not read JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("ERROR: evidence bundle must be a JSON object", file=sys.stderr)
        return 2

    errors = validate_bundle(data)
    if errors:
        print("Evidence bundle rejected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Evidence bundle accepted: structural gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
