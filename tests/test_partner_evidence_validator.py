from __future__ import annotations

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
                "signed_by_ward": False,
            },
        },
    }


def test_valid_evidence_bundle_passes() -> None:
    assert validate_bundle(valid_bundle()) == []


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


def test_requires_all_nine_checks() -> None:
    bundle = valid_bundle()
    bundle["ward_result"]["checks"] = bundle["ward_result"]["checks"][:8]

    errors = validate_bundle(bundle)

    assert "ward_result.checks must contain exactly steps 1 through 9" in errors
