#!/usr/bin/env python3
"""Validate a Ward design-partner evidence bundle.

This is an offline structural gate. It does not query XRPL and it does not
prove a ledger state by itself. Its job is to reject evidence bundles that are
not reproducible, contain secrets, use simulated language, or blur the
`ward_signed = False` boundary.
"""

from __future__ import annotations

import argparse
import hashlib
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


def _is_non_mainnet(network: Any) -> bool:
    if not isinstance(network, dict):
        return False
    name = str(network.get("name", "")).strip().lower()
    return bool(name) and "mainnet" not in name


def _validate_raw_reads_archive(
    bundle: dict[str, Any], bundle_path: Path | None
) -> list[str]:
    errors: list[str] = []
    if bundle_path is None:
        return [
            "non-mainnet evidence requires its bundle path to validate the raw-read archive"
        ]

    source = bundle.get("source")
    archive_ref = source.get("raw_reads_archive") if isinstance(source, dict) else None
    if not isinstance(archive_ref, dict):
        return ["non-mainnet evidence requires source.raw_reads_archive"]

    expected_path = bundle_path.with_name(f"{bundle_path.stem}.raw-reads.json")
    if archive_ref.get("file") != expected_path.name:
        errors.append(f"source.raw_reads_archive.file must be {expected_path.name}")
    if archive_ref.get("schema") != "ward-raw-ledger-reads/v1":
        errors.append(
            'source.raw_reads_archive.schema must be "ward-raw-ledger-reads/v1"'
        )
    if archive_ref.get("complete") is not True:
        errors.append("source.raw_reads_archive.complete must be true")
    if not expected_path.is_file():
        errors.append(f"required raw-read archive is missing: {expected_path}")
        return errors

    try:
        archive_bytes = expected_path.read_bytes()
        archive = json.loads(archive_bytes)
    except Exception as exc:  # noqa: BLE001 - structural gate should explain failures
        errors.append(f"could not read raw-read archive: {exc}")
        return errors
    if not isinstance(archive, dict):
        errors.append("raw-read archive must be a JSON object")
        return errors

    expected_hash = archive_ref.get("sha256")
    actual_hash = hashlib.sha256(archive_bytes).hexdigest()
    if not isinstance(expected_hash, str) or expected_hash != actual_hash:
        errors.append("raw-read archive SHA-256 does not match evidence bundle")
    if archive.get("schema") != "ward-raw-ledger-reads/v1":
        errors.append('raw-read archive schema must be "ward-raw-ledger-reads/v1"')
    if archive.get("certificate_file") != bundle_path.name:
        errors.append(
            "raw-read archive certificate_file does not match evidence bundle"
        )
    if archive.get("network") != bundle.get("network"):
        errors.append("raw-read archive network does not match evidence bundle")
    reads = archive.get("reads")
    if not isinstance(reads, list) or not reads:
        errors.append("raw-read archive reads must be a non-empty list")
    else:
        for index, read in enumerate(reads):
            if not isinstance(read, dict):
                errors.append(f"raw-read archive reads[{index}] must be an object")
                continue
            if not isinstance(read.get("request"), dict):
                errors.append(
                    f"raw-read archive reads[{index}].request must be an object"
                )
            if "response" not in read and "error" not in read:
                errors.append(
                    f"raw-read archive reads[{index}] must contain response or error"
                )

    completeness = archive.get("completeness")
    if not isinstance(completeness, dict):
        errors.append("raw-read archive completeness must be an object")
    else:
        if completeness.get("complete") is not True:
            errors.append("raw-read archive completeness.complete must be true")
        if completeness.get("errors"):
            errors.append("raw-read archive completeness.errors must be empty")

    return errors


def _validate_settlement_packet(ward_result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    approved = ward_result.get("approved") is True
    settlement = ward_result.get("settlement")
    if not isinstance(settlement, dict):
        return errors

    packet_present = settlement.get("unsigned_packet_present")
    packet = settlement.get("unsigned_packet")
    if not isinstance(packet_present, bool):
        errors.append("ward_result.settlement.unsigned_packet_present must be boolean")
        return errors

    if not approved:
        if packet_present is not False:
            errors.append("rejected evidence must not report an unsigned packet")
        if packet not in (None, {}):
            errors.append("rejected evidence must not contain an unsigned packet")
        return errors

    if packet_present is not True:
        errors.append("approved evidence requires an unsigned settlement packet")
    if not isinstance(packet, dict):
        errors.append(
            "approved evidence requires ward_result.settlement.unsigned_packet"
        )
        return errors

    if packet.get("ward_signed") is not False:
        errors.append("unsigned settlement packet ward_signed must be false")
    if packet.get("rail") != "xrpl":
        errors.append('unsigned settlement packet rail must be "xrpl"')
    if packet.get("action_type") != "xrpl.pool_release":
        errors.append(
            'unsigned settlement packet action_type must be "xrpl.pool_release"'
        )
    signer = packet.get("signer")
    if not isinstance(signer, str) or not signer:
        errors.append("unsigned settlement packet signer is required")

    payload = packet.get("payload")
    if not isinstance(payload, dict):
        errors.append("unsigned settlement packet payload must be an object")
        return errors
    if payload.get("TransactionType") != "Payment":
        errors.append("unsigned settlement packet must contain a Payment transaction")
    if payload.get("Account") != signer:
        errors.append("unsigned settlement packet Account must match signer")
    if not payload.get("Destination"):
        errors.append("unsigned settlement packet Destination is required")
    amount = payload.get("Amount")
    if not isinstance(amount, str) or not amount.isdigit() or int(amount) <= 0:
        errors.append("unsigned settlement packet Amount must be positive drops")

    prohibited = {"signature", "txnsignature", "signingpubkey", "signers"}
    for path, value in _walk(payload, "ward_result.settlement.unsigned_packet.payload"):
        key = path.rsplit(".", 1)[-1]
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized in prohibited and value not in (None, "", [], {}):
            errors.append(
                f"unsigned settlement packet contains signing material: {path}"
            )

    return errors


def validate_bundle(
    bundle: dict[str, Any], *, bundle_path: Path | None = None
) -> list[str]:
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
        errors.extend(_validate_settlement_packet(ward_result))

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
                    errors.append(
                        f"ward_result.checks[{index}].number must be an integer"
                    )
                if check.get("status") not in {"passed", "failed", "not_applicable"}:
                    errors.append(
                        f"ward_result.checks[{index}].status must be passed, failed, or not_applicable"
                    )
            expected_numbers = set(range(1, 10))
            if numbers != expected_numbers:
                errors.append(
                    "ward_result.checks must contain exactly steps 1 through 9"
                )

    for path, value in _walk(bundle):
        if FORBIDDEN_KEY_PATTERN.search(path):
            errors.append(f"secret-like field is forbidden: {path}")
        if isinstance(value, str) and FORBIDDEN_VALUE_PATTERN.search(value):
            errors.append(f"simulated or placeholder language is forbidden at {path}")

    if _is_non_mainnet(bundle.get("network")):
        errors.extend(_validate_raw_reads_archive(bundle, bundle_path))

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

    errors = validate_bundle(data, bundle_path=args.bundle)
    if errors:
        print("Evidence bundle rejected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Evidence bundle accepted: structural gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
