"""XLS-70 eligibility pre-gate + credential verification tests.

Covers ward/credentials.py verification logic and the WARD_REQUIRE_CREDENTIAL
gate behaviour. Uses a fake client so no live ledger is needed.
"""
import pytest

from ward.constants import LSF_CREDENTIAL_ACCEPTED
from ward.credentials import verify_xls70_credential, CredentialResult


ISSUER = "rISABEL00000000000000000000000000"
CLAIMANT = "rALICE000000000000000000000000000"
CRED_TYPE = "4B5943"  # "KYC" in hex


class _FakeResp:
    def __init__(self, objects):
        self._objects = objects

    def is_successful(self):
        return True

    @property
    def result(self):
        return {"account_objects": self._objects}


class _FakeClient:
    """Returns a fixed account_objects list; close_time fixed for expiry tests."""
    def __init__(self, objects, close_time=1_000_000):
        self._objects = objects
        self._close_time = close_time

    async def request(self, req):
        return _FakeResp(self._objects)


def _credential(*, accepted=True, expiration=None, issuer=ISSUER, ctype=CRED_TYPE):
    flags = LSF_CREDENTIAL_ACCEPTED if accepted else 0
    obj = {
        "LedgerEntryType": "Credential",
        "Issuer": issuer,
        "CredentialType": ctype,
        "Flags": flags,
    }
    if expiration is not None:
        obj["Expiration"] = expiration
    return obj


@pytest.mark.asyncio
async def test_valid_credential_passes():
    client = _FakeClient([_credential()])
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is True


@pytest.mark.asyncio
async def test_missing_credential_rejected():
    client = _FakeClient([])  # no credentials at all
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is False
    assert "No XLS-70 credential" in res.reason


@pytest.mark.asyncio
async def test_wrong_issuer_rejected():
    client = _FakeClient([_credential(issuer="rWRONGISSUER0000000000000000000000")])
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is False


@pytest.mark.asyncio
async def test_unaccepted_credential_rejected():
    client = _FakeClient([_credential(accepted=False)])
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is False
    assert "not accepted" in res.reason


@pytest.mark.asyncio
async def test_expired_credential_rejected(monkeypatch):
    # Credential expired at ripple-time 500_000; close_time is 1_000_000.
    import ward.credentials as creds

    async def _fake_close_time(client):
        return 1_000_000

    monkeypatch.setattr(creds, "get_ledger_close_time", _fake_close_time)
    client = _FakeClient([_credential(expiration=500_000)])
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is False
    assert "expired" in res.reason


@pytest.mark.asyncio
async def test_unexpired_credential_passes(monkeypatch):
    import ward.credentials as creds

    async def _fake_close_time(client):
        return 1_000_000

    monkeypatch.setattr(creds, "get_ledger_close_time", _fake_close_time)
    # Expires in the future relative to close_time.
    client = _FakeClient([_credential(expiration=2_000_000)])
    res = await verify_xls70_credential(client, CLAIMANT, ISSUER, CRED_TYPE)
    assert res.valid is True
