from __future__ import annotations

import json

from scripts.verify_devnet_evidence_independent import _policy_commitment, verify


def _verify(lifecycle: dict, ward_bundle: dict, *, verifier_role: str = "independent"):
    return verify(lifecycle, ward_bundle, verifier_role=verifier_role)

POLICY_ID = "F" * 64
VAULT_ID = "A" * 64
BROKER_ID = "B" * 64
LOAN_ID = "C" * 64
POOL = "rPool"
CLAIMANT = "rClaimant"
VAULT_OWNER = "rVaultOwner"


def lifecycle_fixture() -> dict:
    return {
        "meta": {
            "default_resolution_submitted": False,
            "pre_resolution_ledger_close_time": 1120,
        },
        "tx_results": {
            "VaultCreate": {"engine_result": "tesSUCCESS", "raw": {}},
            "VaultDeposit": {"engine_result": "tesSUCCESS", "raw": {}},
            "LoanBrokerSet": {"engine_result": "tesSUCCESS", "raw": {}},
            "LoanBrokerCoverDeposit": {"engine_result": "tesSUCCESS", "raw": {}},
            "LoanSet": {"engine_result": "tesSUCCESS", "raw": {}},
            "WardPolicyNFTokenMint": {
                "engine_result": "tesSUCCESS",
                "raw": {
                    "meta": {"nftoken_id": POLICY_ID},
                    "tx_json": {
                        "Account": CLAIMANT,
                        "NFTokenTaxon": 281,
                        "URI": (
                            "7B2277223A22776172642D7631222C2276223A22725661756C744F776E6572"
                            "222C2263223A2232303030303030222C2265223A3939393939393939392C"
                            "2274223A2273746172746572222C227061223A2272506F6F6C227D"
                        ),
                    },
                },
            },
            "WardPolicyPremiumPayment": {
                "engine_result": "tesSUCCESS",
                "raw": {
                    "meta": {
                        "AffectedNodes": [
                            {
                                "ModifiedNode": {
                                    "FinalFields": {
                                        "Account": POOL,
                                        "Balance": "3000000",
                                    }
                                }
                            }
                        ]
                    },
                    "tx_json": {
                        "TransactionType": "Payment",
                        "Account": CLAIMANT,
                        "Destination": POOL,
                        "Memos": [
                            {
                                "Memo": {
                                    "MemoType": "776172642F706F6C6963792D7072656D69756D",
                                    "MemoData": (
                                        POLICY_ID.encode().hex().upper()
                                        + "3A32303030303030"
                                    ),
                                }
                            }
                        ],
                    },
                },
            },
        },
        "ledger_objects": {
            "Vault": {"index": VAULT_ID, "Owner": VAULT_OWNER},
            "LoanBroker": {"index": BROKER_ID, "VaultID": VAULT_ID},
            "Loan_pre_default_resolution": {
                "Borrower": CLAIMANT,
                "LoanBrokerID": BROKER_ID,
                "NextPaymentDueDate": 1000,
                "GracePeriod": 60,
                "TotalValueOutstanding": "1000001",
            },
        },
        "ward_policy": {
            "policy_nft_id": POLICY_ID,
            "pool_address": POOL,
            "claimant_address": CLAIMANT,
            "defaulted_vault": VAULT_OWNER,
            "coverage_drops": 2_000_000,
            "expiry_ledger_time": 999_999_999,
            "nft_taxon": 281,
            "ward_signed": False,
        },
    }


def ward_bundle_fixture() -> dict:
    return {
        "objects": {
            "loan_id": LOAN_ID,
            "policy_nft_id": POLICY_ID,
        },
        "ward_result": {
            "approved": True,
            "ward_signed": False,
            "claim_payout_drops": 1_000_001,
            "vault_loss_drops": 1_000_001,
            "settlement": {
                "unsigned_packet_present": True,
                "unsigned_packet": {
                    "action_type": "xrpl.pool_release",
                    "rail": "xrpl",
                    "signer": POOL,
                    "payload": {
                        "TransactionType": "Payment",
                        "Account": POOL,
                        "Destination": CLAIMANT,
                        "Amount": "1000001",
                        "Memos": [
                            {
                                "Memo": {
                                    "MemoData": (
                                        '{"loan_id":"'
                                        + LOAN_ID
                                        + '","policy_nft_id":"'
                                        + POLICY_ID
                                        + '"}'
                                    )
                                    .encode()
                                    .hex()
                                }
                            }
                        ],
                    },
                    "ward_signed": False,
                },
                "signed_by_ward": False,
            },
        },
    }


def test_independent_verifier_derives_same_result_without_trusting_checks() -> None:
    report = _verify(lifecycle_fixture(), ward_bundle_fixture())

    assert report["approved_by_ward"] is True
    assert report["independently_verified"] is True
    assert report["derived"]["claim_payout_drops"] == 1_000_001
    assert report["derived"]["policy_coverage_drops"] == 2_000_000
    assert {check["status"] for check in report["checks"]} == {"passed"}


def test_independent_verifier_rejects_before_grace_elapsed() -> None:
    lifecycle = lifecycle_fixture()
    lifecycle["meta"]["pre_resolution_ledger_close_time"] = 1059

    report = _verify(lifecycle, ward_bundle_fixture())

    assert report["independently_verified"] is False
    assert "pre_resolution_default_ready" in report["failures"]


def test_independent_verifier_rejects_overstated_payout() -> None:
    ward_bundle = ward_bundle_fixture()
    ward_bundle["ward_result"]["claim_payout_drops"] = 2_000_001

    report = _verify(lifecycle_fixture(), ward_bundle)

    assert report["independently_verified"] is False
    assert "loss_math_bounded" in report["failures"]


def test_independent_verifier_rejects_packet_with_wrong_destination() -> None:
    ward_bundle = ward_bundle_fixture()
    ward_bundle["ward_result"]["settlement"]["unsigned_packet"]["payload"][
        "Destination"
    ] = "rWrongClaimant"

    report = _verify(lifecycle_fixture(), ward_bundle)

    assert report["independently_verified"] is False
    assert "unsigned_packet_matches_resolution" in report["failures"]


def test_independent_verifier_rejects_packet_signing_material() -> None:
    ward_bundle = ward_bundle_fixture()
    ward_bundle["ward_result"]["settlement"]["unsigned_packet"]["payload"][
        "TxnSignature"
    ] = "DEADBEEF"

    report = _verify(lifecycle_fixture(), ward_bundle)

    assert report["independently_verified"] is False
    assert "unsigned_packet_matches_resolution" in report["failures"]


def test_independent_verifier_accepts_ward_v2_premium_binding() -> None:
    lifecycle = lifecycle_fixture()
    premium_hash = "D" * 64
    metadata = {
        "w": "ward-v2",
        "v": VAULT_OWNER,
        "c": "2000000",
        "e": 999_999_999,
        "t": "starter",
        "pa": POOL,
        "p": premium_hash,
    }
    commitment = _policy_commitment(metadata)
    lifecycle["tx_results"]["WardPolicyNFTokenMint"]["raw"]["tx_json"][
        "URI"
    ] = json.dumps(metadata, separators=(",", ":")).encode().hex().upper()
    lifecycle["tx_results"]["WardPolicyPremiumPayment"]["hash"] = premium_hash
    lifecycle["tx_results"]["WardPolicyPremiumPayment"]["raw"]["tx_json"][
        "Memos"
    ][0]["Memo"]["MemoData"] = (
        commitment.encode().hex().upper() + "3A32303030303030"
    )

    report = _verify(lifecycle, ward_bundle_fixture())

    assert report["independently_verified"] is True


def test_operator_receipt_independently_verified_is_false_even_when_checks_pass() -> None:
    report = _verify(
        lifecycle_fixture(),
        ward_bundle_fixture(),
        verifier_role="operator",
    )

    assert report["verifier_role"] == "operator"
    assert report["independently_verified"] is False
    assert report["ward_signed"] is False
    assert {check["status"] for check in report["checks"]} == {"passed"}
    assert report["failures"] == []


def test_independent_path_may_set_independently_verified_true() -> None:
    report = _verify(
        lifecycle_fixture(),
        ward_bundle_fixture(),
        verifier_role="independent",
    )

    assert report["verifier_role"] == "independent"
    assert report["independently_verified"] is True
    assert report["ward_signed"] is False



def test_cli_requires_explicit_verifier_role(tmp_path, monkeypatch, capsys) -> None:
    """No silent default to "independent" (that default mislabeled 09-01)."""
    import sys

    import pytest

    from scripts import verify_devnet_evidence_independent as cli

    monkeypatch.setattr(sys, "argv", ["verify", "a.json", "b.json"])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 2
    assert "--verifier-role" in capsys.readouterr().err


def test_cli_operator_run_exits_zero_when_checks_pass(monkeypatch, capsys) -> None:
    """Operator runs are labeled independently_verified=false but still exit 0."""
    import json
    import sys
    from pathlib import Path

    from scripts import verify_devnet_evidence_independent as cli

    root = Path(__file__).resolve().parents[1] / "docs/security/evidence/devnet/2026-09-02"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify",
            str(root / "phase1-devnet-pre-resolution-2026-09-02.json"),
            str(root / "ward-evidence-pre-resolution-2026-09-02.json"),
            "--verifier-role",
            "operator",
        ],
    )
    assert cli.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["failures"] == []
    assert report["verifier_role"] == "operator"
    assert report["independently_verified"] is False
    assert report["ward_signed"] is False
