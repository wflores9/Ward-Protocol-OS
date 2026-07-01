"""
Ward Protocol SDK — API route smoke tests.
Tests the canonical /purchase and /validate routes with correct parameters.
ward_signed = False — always.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

VALID_ADDRESS = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
VALID_ADDRESS2 = "rU6K7V3Po4snVhBBaU29sesqs2qTQJWDw1"


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ward_signed"] is False


def test_purchase_requires_auth():
    resp = client.post(
        "/purchase",
        json={
            "vault_id": VALID_ADDRESS,
            "pool_address": VALID_ADDRESS2,
            "coverage_drops": 1000000,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["ward_signed"] is False


def test_validate_requires_auth():
    resp = client.post(
        "/validate",
        json={
            "vault_id": VALID_ADDRESS,
            "policy_nft_id": "A" * 64,
            "claimant_address": VALID_ADDRESS,
            "loan_id": "B" * 64,
            "pool_address": VALID_ADDRESS2,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["ward_signed"] is False


def test_invalid_vault_address_rejected():
    resp = client.get("/dashboard/vault/not-a-real-address/health")
    assert resp.status_code == 422
    assert resp.json()["detail"]["ward_signed"] is False


def test_404_includes_ward_signed():
    resp = client.get("/nonexistent-route")
    assert resp.status_code == 404
    assert resp.json()["ward_signed"] is False
