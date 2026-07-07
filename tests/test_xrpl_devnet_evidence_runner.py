from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

import scripts.run_xrpl_devnet_evidence as evidence_runner
from scripts.run_xrpl_devnet_evidence import UNPROVIDED, build_bundle
from scripts.validate_partner_evidence import validate_bundle


def lifecycle_fixture(tmp_path, *, include_ward_policy=False):
    path = tmp_path / "lifecycle.json"
    lifecycle = {
        "meta": {"network": "devnet"},
        "wallets": {
            "vault_owner": {
                "address": "rVaultOwner",
                "seed": "REDACTED_DEVNET_FAUCET_SEED",
            },
            "borrower": {
                "address": "rBorrower",
                "seed": "REDACTED_DEVNET_FAUCET_SEED",
            },
        },
        "tx_results": {
            "VaultCreate": {
                "hash": "A" * 64,
                "engine_result": "tesSUCCESS",
                "raw": {"ledger_index": 10},
            },
            "LoanSet": {
                "hash": "B" * 64,
                "engine_result": "tesSUCCESS",
                "raw": {
                    "ledger_index": 11,
                    "meta": {
                        "AffectedNodes": [
                            {
                                "CreatedNode": {
                                    "LedgerEntryType": "Loan",
                                    "LedgerIndex": "C" * 64,
                                }
                            }
                        ]
                    },
                },
            },
        },
        "ledger_objects": {
            "Vault": {"index": "D" * 64},
            "LoanBroker": {"index": "E" * 64},
        },
    }
    if include_ward_policy:
        lifecycle["ward_policy"] = {
            "policy_nft_id": "F" * 64,
            "pool_address": "rPoolFromArtifact",
            "claimant_address": "rClaimantFromArtifact",
            "defaulted_vault": "rVaultFromArtifact",
        }
    path.write_text(json.dumps(lifecycle), encoding="utf-8")
    return path


def args_for(path, out, **overrides):
    defaults = {
        "lifecycle": path,
        "out": out,
        "allow_incomplete": True,
        "query_devnet": False,
        "vault_id": None,
        "loan_broker_id": None,
        "loan_id": None,
        "policy_nft_id": None,
        "pool_address": None,
        "claimant_address": None,
        "defaulted_vault": None,
        "xrpl_json_rpc_url": "https://s.devnet.rippletest.net:51234",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.asyncio
async def test_incomplete_lifecycle_bundle_is_fail_closed_and_structurally_valid(tmp_path):
    lifecycle = lifecycle_fixture(tmp_path)
    bundle = await build_bundle(args_for(lifecycle, tmp_path / "evidence.json"))

    assert bundle["ward_result"]["approved"] is False
    assert bundle["ward_result"]["ward_signed"] is False
    assert bundle["ward_result"]["steps_passed"] == 0
    assert bundle["objects"]["policy_nft_id"] == UNPROVIDED
    assert bundle["ward_result"]["checks"][0]["status"] == "failed"
    assert validate_bundle(bundle) == []


@pytest.mark.asyncio
async def test_complete_inputs_use_canonical_validator_result(tmp_path, monkeypatch):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id):
        assert loan_id == "C" * 64
        assert args.policy_nft_id == "F" * 64
        assert args.pool_address == "rPool"
        assert args.claimant_address == "rClaimant"
        assert args.defaulted_vault == "rVault"
        return SimpleNamespace(
            approved=False,
            steps_passed=3,
            rejection_reason="Loan default flag not set on-chain.",
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    bundle = await build_bundle(
        args_for(
            lifecycle,
            tmp_path / "evidence.json",
            allow_incomplete=False,
            policy_nft_id="F" * 64,
            pool_address="rPool",
            claimant_address="rClaimant",
            defaulted_vault="rVault",
        )
    )

    assert bundle["source"]["complete_ward_inputs"] is True
    assert bundle["ward_result"]["approved"] is False
    assert bundle["ward_result"]["steps_passed"] == 3
    assert bundle["ward_result"]["checks"][3]["status"] == "failed"
    assert bundle["ward_result"]["rejection_reason"] == "Loan default flag not set on-chain."
    assert bundle["ward_result"]["settlement"]["signed_by_ward"] is False
    assert validate_bundle(bundle) == []


@pytest.mark.asyncio
async def test_complete_inputs_default_from_lifecycle_policy_artifact(tmp_path, monkeypatch):
    lifecycle = lifecycle_fixture(tmp_path, include_ward_policy=True)

    async def fake_validation(args, loan_id):
        assert args.policy_nft_id == "F" * 64
        assert args.pool_address == "rPoolFromArtifact"
        assert args.claimant_address == "rClaimantFromArtifact"
        assert args.defaulted_vault == "rVaultFromArtifact"
        return SimpleNamespace(
            approved=False,
            steps_passed=2,
            rejection_reason="Cross-vault claim rejected.",
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    bundle = await build_bundle(
        args_for(
            lifecycle,
            tmp_path / "evidence.json",
            allow_incomplete=False,
        )
    )

    assert bundle["source"]["complete_ward_inputs"] is True
    assert bundle["objects"]["pool_address"] == "rPoolFromArtifact"
    assert bundle["objects"]["claimant_address"] == "rClaimantFromArtifact"
    assert bundle["objects"]["defaulted_vault"] == "rVaultFromArtifact"
    assert bundle["ward_result"]["steps_passed"] == 2
    assert validate_bundle(bundle) == []


@pytest.mark.asyncio
async def test_complete_inputs_can_emit_approved_canonical_bundle(tmp_path, monkeypatch):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id):
        return SimpleNamespace(
            approved=True,
            steps_passed=9,
            rejection_reason="",
            claim_payout_drops=500_000,
            vault_loss_drops=750_000,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    bundle = await build_bundle(
        args_for(
            lifecycle,
            tmp_path / "evidence.json",
            allow_incomplete=False,
            policy_nft_id="F" * 64,
            pool_address="rPool",
            claimant_address="rClaimant",
            defaulted_vault="rVault",
        )
    )

    assert bundle["ward_result"]["approved"] is True
    assert bundle["ward_result"]["steps_passed"] == 9
    assert {check["status"] for check in bundle["ward_result"]["checks"]} == {"passed"}
    assert bundle["ward_result"]["settlement"]["signed_by_ward"] is False
    assert validate_bundle(bundle) == []


@pytest.mark.asyncio
async def test_missing_inputs_require_explicit_incomplete_mode(tmp_path):
    lifecycle = lifecycle_fixture(tmp_path)

    with pytest.raises(SystemExit):
        await build_bundle(
            args_for(lifecycle, tmp_path / "evidence.json", allow_incomplete=False)
        )
