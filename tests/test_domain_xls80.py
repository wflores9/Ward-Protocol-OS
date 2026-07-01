"""XLS-80 permissioned-domain membership tests.

Covers ward/credentials.py domain verification: real PermissionedDomain
object read, AcceptedCredentials matching (reusing XLS-70 verification),
and the compliance audit record. Uses fake clients — no live ledger.
"""
import pytest

from ward.constants import LSF_CREDENTIAL_ACCEPTED
from ward.credentials import verify_xls80_domain_membership, DomainResult


ISSUER = "rISABEL00000000000000000000000000"
CLAIMANT = "rALICE000000000000000000000000000"
CRED_TYPE = "4B5943"  # "KYC" hex
DOMAIN_ID = "ABCDEF1234567890" + "0" * 48


class _Resp:
    def __init__(self, result, ok=True):
        self._result = result
        self._ok = ok

    def is_successful(self):
        return self._ok

    @property
    def result(self):
        return self._result


class _DomainClient:
    """Serves a PermissionedDomain via LedgerEntry, and the claimant's
    credentials via AccountObjects — routed by request type name."""
    def __init__(self, domain_node, credentials, domain_ok=True):
        self._domain_node = domain_node
        self._credentials = credentials
        self._domain_ok = domain_ok

    async def request(self, req):
        name = type(req).__name__
        if name == "LedgerEntry":
            if not self._domain_ok:
                return _Resp({}, ok=False)
            return _Resp({"node": self._domain_node})
        if name == "AccountObjects":
            return _Resp({"account_objects": self._credentials})
        raise AssertionError(f"unexpected request type: {name}")


def _accepted_creds(*pairs):
    return [
        {"Credential": {"Issuer": iss, "CredentialType": ct}} for iss, ct in pairs
    ]


def _domain_node(accepted):
    return {
        "LedgerEntryType": "PermissionedDomain",
        "Owner": "rOWEN000000000000000000000000000",
        "AcceptedCredentials": accepted,
    }


def _held_credential(issuer=ISSUER, ctype=CRED_TYPE, accepted=True):
    return [{
        "LedgerEntryType": "Credential",
        "Issuer": issuer,
        "CredentialType": ctype,
        "Flags": LSF_CREDENTIAL_ACCEPTED if accepted else 0,
    }]


@pytest.mark.asyncio
async def test_domain_member_passes_with_audit_record():
    client = _DomainClient(
        domain_node=_domain_node(_accepted_creds((ISSUER, CRED_TYPE))),
        credentials=_held_credential(),
    )
    res = await verify_xls80_domain_membership(client, CLAIMANT, DOMAIN_ID)
    assert res.member is True
    # Audit record captured which credential satisfied membership.
    assert res.matched_issuer == ISSUER
    assert res.matched_credential_type == CRED_TYPE


@pytest.mark.asyncio
async def test_non_member_rejected():
    # Domain accepts ISSUER/CRED_TYPE, but claimant holds none.
    client = _DomainClient(
        domain_node=_domain_node(_accepted_creds((ISSUER, CRED_TYPE))),
        credentials=[],  # holds no credentials
    )
    res = await verify_xls80_domain_membership(client, CLAIMANT, DOMAIN_ID)
    assert res.member is False
    assert "no valid credential" in res.reason.lower()


@pytest.mark.asyncio
async def test_credential_not_accepted_by_domain():
    # Claimant holds a credential, but from an issuer the domain doesn't accept.
    client = _DomainClient(
        domain_node=_domain_node(_accepted_creds(("rOTHERISSUER000000000000000000000", CRED_TYPE))),
        credentials=_held_credential(),  # ISSUER, not rOTHER
    )
    res = await verify_xls80_domain_membership(client, CLAIMANT, DOMAIN_ID)
    assert res.member is False


@pytest.mark.asyncio
async def test_missing_domain_rejected():
    client = _DomainClient(
        domain_node={},
        credentials=_held_credential(),
        domain_ok=False,  # LedgerEntry fails -> domain not found
    )
    res = await verify_xls80_domain_membership(client, CLAIMANT, DOMAIN_ID)
    assert res.member is False
    assert "not found" in res.reason.lower()


@pytest.mark.asyncio
async def test_wrong_object_type_rejected():
    client = _DomainClient(
        domain_node={"LedgerEntryType": "Escrow"},  # not a PermissionedDomain
        credentials=_held_credential(),
    )
    res = await verify_xls80_domain_membership(client, CLAIMANT, DOMAIN_ID)
    assert res.member is False
    assert "not a permissioneddomain" in res.reason.lower()
