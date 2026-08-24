from __future__ import annotations

import hashlib
import json

from scripts.validate_partner_evidence import validate_bundle


def valid_bundle() -> dict:
    return {
        "protocol": "Ward Protocol",
        "evidence_type": "xrpl-devnet-lifecycle",
        "generated_at": "2026-07-06T00:00:00Z",
        "commit": "abc1234",
        "network": {
            "name": "XRPL Devnet",
            "rpc_url": "wss://s.devnet.rippletest.net:51233",
            "ledger_index": 123456,
        },
        "source": {
            "tool": "partner-xls66-flow",
            "unaffiliated_reference": True,
        },
        "objects": {
            "vault_id": "A" * 64,
            "loan_broker_id": "B" * 64,
            "loan_id": "C" * 64,
            "policy_nft_id": "D" * 64,
            "pool_address": "rPoolAddress",
            "claimant_address": "rClaimant",
            "defaulted_vault": "rVault",
        },
        "transactions": [
            {
                "hash": "E" * 64,
                "type": "LoanManage",
                "ledger_index": 123456,
            }
        ],
        "ward_result": {
            "ward_signed": False,
            "approved": True,
            "steps_passed": 9,
            "rejection_reason": "",
            "checks": [
                {"number": number, "label": f"Check {number}", "status": "passed"}
                for number in range(1, 10)
            ],
            "settlement": {
                "unsigned_packet_present": True,
                "unsigned_packet": {
                    "action_type": "xrpl.pool_release",
                    "rail": "xrpl",
                    "signer": "rPoolAddress",
                    "payload": {
                        "TransactionType": "Payment",
                        "Account": "rPoolAddress",
                        "Destination": "rClaimant",
                        "Amount": "1000000",
                    },
                    "ward_signed": False,
                },
                "signed_by_ward": False,
            },
        },
    }


def write_bundle_and_archive(tmp_path, bundle, *, complete=True, reads=None):
    bundle_path = tmp_path / "partner-evidence.json"
    archive_path = tmp_path / "partner-evidence.raw-reads.json"
    archive = {
        "schema": "ward-raw-ledger-reads/v1",
        "generated_at": "2026-07-06T00:00:00Z",
        "certificate_file": bundle_path.name,
        "network": bundle["network"],
        "reads": (
            reads
            if reads is not None
            else [
                {
                    "source": "canonical_validator",
                    "transport": "json-rpc",
                    "request": {"method": "ledger"},
                    "response": {"result": {"ledger_index": 123456}},
                }
            ]
        ),
        "completeness": {
            "complete": complete,
            "errors": [] if complete else ["missing"],
        },
    }
    archive_text = json.dumps(archive, indent=2) + "\n"
    archive_path.write_text(archive_text, encoding="utf-8")
    bundle["source"]["raw_reads_archive"] = {
        "file": archive_path.name,
        "schema": "ward-raw-ledger-reads/v1",
        "sha256": hashlib.sha256(archive_text.encode("utf-8")).hexdigest(),
        "complete": complete,
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle_path


def test_valid_evidence_bundle_passes(tmp_path) -> None:
    bundle = valid_bundle()
    bundle_path = write_bundle_and_archive(tmp_path, bundle)

    assert validate_bundle(bundle, bundle_path=bundle_path) == []


def test_non_mainnet_evidence_requires_companion_archive(tmp_path) -> None:
    bundle = valid_bundle()
    bundle_path = tmp_path / "partner-evidence.json"

    errors = validate_bundle(bundle, bundle_path=bundle_path)

    assert "non-mainnet evidence requires source.raw_reads_archive" in errors


def test_rejects_incomplete_raw_read_archive(tmp_path) -> None:
    bundle = valid_bundle()
    bundle_path = write_bundle_and_archive(tmp_path, bundle, complete=False)

    errors = validate_bundle(bundle, bundle_path=bundle_path)

    assert "source.raw_reads_archive.complete must be true" in errors
    assert "raw-read archive completeness.complete must be true" in errors


def test_rejects_raw_read_without_response_or_error(tmp_path) -> None:
    bundle = valid_bundle()
    bundle_path = write_bundle_and_archive(
        tmp_path,
        bundle,
        reads=[{"source": "canonical_validator", "request": {"method": "ledger"}}],
    )

    errors = validate_bundle(bundle, bundle_path=bundle_path)

    assert "raw-read archive reads[0] must contain response or error" in errors


def test_rejects_secret_fields() -> None:
    bundle = valid_bundle()
    bundle["wallet_seed"] = "sn..."

    errors = validate_bundle(bundle)

    assert any("secret-like field" in error for error in errors)


def test_rejects_simulated_language() -> None:
    bundle = valid_bundle()
    bundle["source"]["tool"] = "mock local demo"

    errors = validate_bundle(bundle)

    assert any("simulated or placeholder" in error for error in errors)


def test_rejects_ward_signed_true() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["ward_signed"] = True

    errors = validate_bundle(bundle)

    assert "ward_result.ward_signed must be false" in errors


def test_approved_evidence_requires_unsigned_packet() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["settlement"]["unsigned_packet_present"] = False
    bundle["ward_result"]["settlement"]["unsigned_packet"] = None

    errors = validate_bundle(bundle)

    assert "approved evidence requires an unsigned settlement packet" in errors
    assert "approved evidence requires ward_result.settlement.unsigned_packet" in errors


def test_rejects_signing_material_in_unsigned_packet() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["settlement"]["unsigned_packet"]["payload"][
        "TxnSignature"
    ] = "DEADBEEF"

    errors = validate_bundle(bundle)

    assert any("contains signing material" in error for error in errors)


def test_rejected_evidence_cannot_carry_unsigned_packet() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["approved"] = False

    errors = validate_bundle(bundle)

    assert "rejected evidence must not report an unsigned packet" in errors
    assert "rejected evidence must not contain an unsigned packet" in errors


def test_requires_all_nine_checks() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["checks"] = bundle["ward_result"]["checks"][:8]

    errors = validate_bundle(bundle)

    assert "ward_result.checks must contain exactly steps 1 through 9" in errors
