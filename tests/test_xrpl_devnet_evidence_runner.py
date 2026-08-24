from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

import scripts.run_xrpl_devnet_evidence as evidence_runner
from scripts.run_xrpl_devnet_evidence import UNPROVIDED, build_bundle, issue_evidence
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
        "raw_reads": [
            {
                "source": "vault_account_objects",
                "transport": "websocket",
                "request": {"method": "account_objects"},
                "response": {"result": {"account_objects": [{"index": "D" * 64}]}},
            },
            {
                "source": "loan_broker_account_objects",
                "transport": "websocket",
                "request": {"method": "account_objects"},
                "response": {"result": {"account_objects": [{"index": "E" * 64}]}},
            },
        ],
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


def record_canonical_read(raw_reads):
    raw_reads.append(
        {
            "source": "canonical_validator",
            "transport": "json-rpc",
            "request": {"method": "account_nfts"},
            "response": {"result": {"status": "success", "account_nfts": []}},
            "claims": ["ward_result"],
        }
    )


@pytest.mark.asyncio
async def test_incomplete_lifecycle_bundle_is_fail_closed_and_structurally_valid(
    tmp_path,
):
    lifecycle = lifecycle_fixture(tmp_path)
    output = tmp_path / "evidence.json"
    bundle, archive_path = await issue_evidence(args_for(lifecycle, output))

    assert bundle["ward_result"]["approved"] is False
    assert bundle["ward_result"]["ward_signed"] is False
    assert bundle["ward_result"]["steps_passed"] == 0
    assert bundle["objects"]["policy_nft_id"] == UNPROVIDED
    assert bundle["ward_result"]["checks"][0]["status"] == "failed"
    assert bundle["ward_result"]["settlement"]["unsigned_packet_present"] is False
    assert bundle["ward_result"]["settlement"]["unsigned_packet"] is None
    assert archive_path == tmp_path / "evidence.raw-reads.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archive["completeness"]["complete"] is True
    assert validate_bundle(bundle, bundle_path=output) == []


@pytest.mark.asyncio
async def test_complete_inputs_use_canonical_validator_result(tmp_path, monkeypatch):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id, raw_reads):
        assert loan_id == "C" * 64
        assert args.policy_nft_id == "F" * 64
        assert args.pool_address == "rPool"
        assert args.claimant_address == "rClaimant"
        assert args.defaulted_vault == "rVault"
        record_canonical_read(raw_reads)
        return SimpleNamespace(
            approved=False,
            steps_passed=3,
            rejection_reason="Loan default flag not set on-chain.",
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    output = tmp_path / "evidence.json"
    bundle, _ = await issue_evidence(
        args_for(
            lifecycle,
            output,
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
    assert (
        bundle["ward_result"]["rejection_reason"]
        == "Loan default flag not set on-chain."
    )
    assert bundle["ward_result"]["settlement"]["signed_by_ward"] is False
    assert bundle["ward_result"]["settlement"]["unsigned_packet_present"] is False
    assert bundle["ward_result"]["settlement"]["unsigned_packet"] is None
    assert validate_bundle(bundle, bundle_path=output) == []


@pytest.mark.asyncio
async def test_complete_inputs_default_from_lifecycle_policy_artifact(
    tmp_path, monkeypatch
):
    lifecycle = lifecycle_fixture(tmp_path, include_ward_policy=True)

    async def fake_validation(args, loan_id, raw_reads):
        assert args.policy_nft_id == "F" * 64
        assert args.pool_address == "rPoolFromArtifact"
        assert args.claimant_address == "rClaimantFromArtifact"
        assert args.defaulted_vault == "rVaultFromArtifact"
        record_canonical_read(raw_reads)
        return SimpleNamespace(
            approved=False,
            steps_passed=2,
            rejection_reason="Cross-vault claim rejected.",
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    output = tmp_path / "evidence.json"
    bundle, _ = await issue_evidence(
        args_for(
            lifecycle,
            output,
            allow_incomplete=False,
        )
    )

    assert bundle["source"]["complete_ward_inputs"] is True
    assert bundle["objects"]["pool_address"] == "rPoolFromArtifact"
    assert bundle["objects"]["claimant_address"] == "rClaimantFromArtifact"
    assert bundle["objects"]["defaulted_vault"] == "rVaultFromArtifact"
    assert bundle["ward_result"]["steps_passed"] == 2
    assert validate_bundle(bundle, bundle_path=output) == []


@pytest.mark.asyncio
async def test_complete_inputs_can_emit_approved_canonical_bundle(
    tmp_path, monkeypatch
):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id, raw_reads):
        record_canonical_read(raw_reads)
        return SimpleNamespace(
            approved=True,
            steps_passed=9,
            rejection_reason="",
            claim_payout_drops=500_000,
            vault_loss_drops=750_000,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    output = tmp_path / "evidence.json"
    bundle, _ = await issue_evidence(
        args_for(
            lifecycle,
            output,
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
    assert bundle["ward_result"]["settlement"]["unsigned_packet_present"] is True
    packet = bundle["ward_result"]["settlement"]["unsigned_packet"]
    assert packet["action_type"] == "xrpl.pool_release"
    assert packet["rail"] == "xrpl"
    assert packet["signer"] == "rPool"
    assert packet["ward_signed"] is False
    assert packet["payload"]["TransactionType"] == "Payment"
    assert packet["payload"]["Account"] == "rPool"
    assert packet["payload"]["Destination"] == "rClaimant"
    assert packet["payload"]["Amount"] == "500000"
    assert "TxnSignature" not in packet["payload"]
    assert "SigningPubKey" not in packet["payload"]
    memo_data = packet["payload"]["Memos"][0]["Memo"]["MemoData"]
    assert json.loads(bytes.fromhex(memo_data)) == {
        "loan_id": "C" * 64,
        "policy_nft_id": "F" * 64,
    }
    assert validate_bundle(bundle, bundle_path=output) == []


@pytest.mark.asyncio
async def test_approved_bundle_refuses_non_positive_packet_amount(
    tmp_path, monkeypatch
):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id, raw_reads):
        record_canonical_read(raw_reads)
        return SimpleNamespace(
            approved=True,
            steps_passed=9,
            rejection_reason="",
            claim_payout_drops=0,
            vault_loss_drops=0,
            policy_coverage_drops=1_000_000,
        )

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)

    with pytest.raises(SystemExit, match="positive claim payout"):
        await issue_evidence(
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


@pytest.mark.asyncio
async def test_approved_bundle_refuses_missing_unsigned_packet(tmp_path, monkeypatch):
    lifecycle = lifecycle_fixture(tmp_path)

    async def fake_validation(args, loan_id, raw_reads):
        record_canonical_read(raw_reads)
        return SimpleNamespace(
            approved=True,
            steps_passed=9,
            rejection_reason="",
            claim_payout_drops=500_000,
            vault_loss_drops=500_000,
            policy_coverage_drops=1_000_000,
        )

    async def missing_packet(**kwargs):
        return None

    monkeypatch.setattr(evidence_runner, "_run_canonical_validation", fake_validation)
    monkeypatch.setattr(
        evidence_runner, "_build_unsigned_settlement_packet", missing_packet
    )

    with pytest.raises(SystemExit, match="without an unsigned settlement packet"):
        await issue_evidence(
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


@pytest.mark.asyncio
async def test_missing_inputs_require_explicit_incomplete_mode(tmp_path):
    lifecycle = lifecycle_fixture(tmp_path)

    with pytest.raises(SystemExit):
        await build_bundle(
            args_for(lifecycle, tmp_path / "evidence.json", allow_incomplete=False)
        )


@pytest.mark.asyncio
async def test_issuance_refuses_missing_raw_transaction_response(tmp_path):
    lifecycle = lifecycle_fixture(tmp_path)
    data = json.loads(lifecycle.read_text(encoding="utf-8"))
    data["tx_results"]["VaultCreate"]["raw"] = {}
    lifecycle.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "evidence.json"

    with pytest.raises(SystemExit, match="Refusing to issue non-mainnet evidence"):
        await issue_evidence(args_for(lifecycle, output))

    assert not output.exists()
    assert not (tmp_path / "evidence.raw-reads.json").exists()


@pytest.mark.asyncio
async def test_issuance_refuses_selected_objects_without_full_rpc_responses(tmp_path):
    lifecycle = lifecycle_fixture(tmp_path)
    data = json.loads(lifecycle.read_text(encoding="utf-8"))
    data["raw_reads"] = []
    lifecycle.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "evidence.json"

    with pytest.raises(SystemExit, match="missing full lifecycle RPC/WS responses"):
        await issue_evidence(args_for(lifecycle, output))

    assert not output.exists()
    assert not (tmp_path / "evidence.raw-reads.json").exists()
