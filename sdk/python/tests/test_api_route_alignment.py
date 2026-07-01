"""
Ward Protocol — API route alignment tests.
Verifies /purchase and /validate call correct SDK interfaces.
ward_signed = False — always.
"""
from pathlib import Path
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

# Set auth env for tests
os.environ["INSTITUTION_API_KEY"] = "test-key"

client = TestClient(main.app)

VALID_ADDRESS = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
VALID_ADDRESS2 = "rU6K7V3Po4snVhBBaU29sesqs2qTQJWDw1"
VALID_NFT_ID = "A" * 64
VALID_LOAN_ID = "B" * 64


def test_purchase_route_returns_unsigned_transactions(monkeypatch):
    captured = {}

    class FakeWardClient:
        def __init__(self, url):
            captured["url"] = url

        async def purchase_coverage(self, **kwargs):
            captured.update(kwargs)
            return {
                "nft_token_id": "pending_institution_signature",
                "mint_tx": "unsigned",
                "coverage_drops": 1000,
                "expiry_ledger": 800000000,
                "ward_signed": False,
            }

    monkeypatch.setattr(main, "WardClient", FakeWardClient)

    resp = client.post(
        "/purchase",
        headers={"X-Institution-Key": "test-key"},
        json={
            "vault_id": VALID_ADDRESS,
            "pool_address": VALID_ADDRESS2,
            "coverage_drops": 1000,
            "duration_days": 30,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ward_signed"] is False
    assert payload["flow"] == "F·03"
    assert "wallet" not in captured
    assert captured["vault_address"] == VALID_ADDRESS
    assert captured["pool_address"] == VALID_ADDRESS2
    assert captured["period_days"] == 30


def test_validate_route_calls_claim_validator(monkeypatch):
    fake_result = MagicMock()
    fake_result.steps_passed = 9
    fake_result.approved = True
    fake_result.claim_payout_drops = 500000
    fake_result.vault_loss_drops = 600000
    fake_result.policy_coverage_drops = 1000000
    fake_result.rejection_reason = ""

    class FakeClaimValidator:
        def __init__(self, url=None):
            pass

        async def validate_claim(self, **kwargs):
            return fake_result

    monkeypatch.setattr(main, "ClaimValidator", FakeClaimValidator)

    resp = client.post(
        "/validate",
        headers={"X-Institution-Key": "test-key"},
        json={
            "vault_id": VALID_ADDRESS,
            "policy_nft_id": VALID_NFT_ID,
            "claimant_address": VALID_ADDRESS,
            "loan_id": VALID_LOAN_ID,
            "pool_address": VALID_ADDRESS2,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ward_signed"] is False
    assert payload["flow"] == "F·05"
    assert payload["checks_total"] == 9
    assert payload["approved"] is True


def test_purchase_requires_auth():
    resp = client.post(
        "/purchase",
        json={"vault_id": VALID_ADDRESS, "pool_address": VALID_ADDRESS2, "coverage_drops": 1000},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["ward_signed"] is False


def test_validate_requires_auth():
    resp = client.post(
        "/validate",
        json={"vault_id": VALID_ADDRESS, "policy_nft_id": VALID_NFT_ID,
              "claimant_address": VALID_ADDRESS, "loan_id": VALID_LOAN_ID,
              "pool_address": VALID_ADDRESS2},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["ward_signed"] is False
