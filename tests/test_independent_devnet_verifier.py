from __future__ import annotations

from scripts.verify_devnet_evidence_independent import verify


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
            "settlement": {"signed_by_ward": False},
        },
    }


def test_independent_verifier_derives_same_result_without_trusting_checks() -> None:
    report = verify(lifecycle_fixture(), ward_bundle_fixture())

    assert report["approved_by_ward"] is True
    assert report["independently_verified"] is True
    assert report["derived"]["claim_payout_drops"] == 1_000_001
    assert report["derived"]["policy_coverage_drops"] == 2_000_000
    assert {check["status"] for check in report["checks"]} == {"passed"}


def test_independent_verifier_rejects_before_grace_elapsed() -> None:
    lifecycle = lifecycle_fixture()
    lifecycle["meta"]["pre_resolution_ledger_close_time"] = 1059

    report = verify(lifecycle, ward_bundle_fixture())

    assert report["independently_verified"] is False
    assert "pre_resolution_default_ready" in report["failures"]


def test_independent_verifier_rejects_overstated_payout() -> None:
    ward_bundle = ward_bundle_fixture()
    ward_bundle["ward_result"]["claim_payout_drops"] = 2_000_001

    report = verify(lifecycle_fixture(), ward_bundle)

    assert report["independently_verified"] is False
    assert "loss_math_bounded" in report["failures"]
