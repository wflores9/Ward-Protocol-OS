"""
ward/credentials.py — XLS-70 On-Chain Credential verification.

Verifies that a claimant holds a valid XLS-70 Credential ledger object:
exists, accepted (lsfAccepted set), and not expired. This is spec-compliant
XLS-70 (Credential objects via account_objects) — NOT the legacy taxon-282
NFT placeholder.

Used by the eligibility pre-gate in ClaimValidator when
WARD_REQUIRE_CREDENTIAL is enabled.

ward_signed = False — always.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from xrpl.models import LedgerEntry
from xrpl.models.requests import AccountObjects

from ward.constants import LSF_CREDENTIAL_ACCEPTED
from ward.primitives import LedgerError, get_ledger_close_time

logger = logging.getLogger("ward.credentials")


@dataclass
class CredentialResult:
    valid: bool
    reason: str = ""


async def verify_xls70_credential(
    client,
    claimant: str,
    issuer: str,
    credential_type_hex: str,
) -> CredentialResult:
    """
    Verify the claimant holds a valid XLS-70 Credential from `issuer`
    of type `credential_type_hex` (hex-encoded CredentialType).

    Checks, in order:
      1. A Credential object with matching Issuer + CredentialType exists
         in the claimant's account_objects.
      2. The lsfAccepted flag is set (credential has been accepted).
      3. Expiration is absent or in the future (vs ledger close_time).
    """
    cred_type = credential_type_hex.upper()
    try:
        resp = await client.request(AccountObjects(account=claimant, type="credential"))
    except Exception as exc:
        raise LedgerError(f"AccountObjects(credential) failed for {claimant}: {exc}")

    if not resp.is_successful():
        raise LedgerError(
            f"AccountObjects(credential) failed for {claimant}: {resp.result}"
        )

    objects = resp.result.get("account_objects", [])

    match = None
    for obj in objects:
        if obj.get("LedgerEntryType") != "Credential":
            continue
        if obj.get("Issuer") != issuer:
            continue
        if str(obj.get("CredentialType", "")).upper() != cred_type:
            continue
        match = obj
        break

    if match is None:
        return CredentialResult(
            valid=False,
            reason=f"No XLS-70 credential from issuer {issuer[:12]}... of required type",
        )

    flags = int(match.get("Flags", 0))
    if not (flags & LSF_CREDENTIAL_ACCEPTED):
        return CredentialResult(
            valid=False,
            reason="XLS-70 credential found but not accepted (lsfAccepted unset)",
        )

    expiration = match.get("Expiration")
    if expiration is not None:
        try:
            close_time = await get_ledger_close_time(client)
        except Exception as exc:
            raise LedgerError(f"Could not read ledger close_time: {exc}")
        # Both Expiration (XLS-70) and close_time are Ripple epoch — compare directly.
        if int(expiration) <= close_time:
            return CredentialResult(
                valid=False,
                reason="XLS-70 credential has expired",
            )

    return CredentialResult(valid=True)


@dataclass
class DomainResult:
    member: bool
    reason: str = ""
    # Compliance record: which accepted credential satisfied membership.
    matched_issuer: str = ""
    matched_credential_type: str = ""


async def verify_xls80_domain_membership(
    client,
    claimant: str,
    domain_id: str,
) -> DomainResult:
    """
    Verify the claimant is a member of the XLS-80 PermissionedDomain `domain_id`.

    Per XLS-80: membership is implicit — an account is a member if it holds a
    valid (accepted, unexpired) credential matching one of the domain's
    AcceptedCredentials entries. There is no explicit join step.

    Returns a DomainResult that records WHICH accepted credential satisfied
    membership, so the resolution carries an auditable compliance record.
    """
    try:
        resp = await client.request(LedgerEntry(index=domain_id))
    except Exception as exc:
        raise LedgerError(f"LedgerEntry(domain) failed for {domain_id[:16]}...: {exc}")

    if not resp.is_successful():
        return DomainResult(
            member=False,
            reason=f"PermissionedDomain {domain_id[:16]}... not found on ledger",
        )

    node = resp.result.get("node", {}) or {}
    if node.get("LedgerEntryType") != "PermissionedDomain":
        return DomainResult(
            member=False,
            reason=f"Object {domain_id[:16]}... is not a PermissionedDomain",
        )

    accepted = node.get("AcceptedCredentials", []) or []
    if not accepted:
        return DomainResult(
            member=False,
            reason="PermissionedDomain has no accepted credentials",
        )

    # Check the claimant against each accepted credential; first valid one
    # confirms membership and becomes the audit record.
    for entry in accepted:
        cred = entry.get("Credential", entry) if isinstance(entry, dict) else {}
        issuer = cred.get("Issuer")
        ctype = cred.get("CredentialType")
        if not issuer or not ctype:
            continue
        result = await verify_xls70_credential(client, claimant, issuer, ctype)
        if result.valid:
            return DomainResult(
                member=True,
                matched_issuer=issuer,
                matched_credential_type=str(ctype),
            )

    return DomainResult(
        member=False,
        reason="Claimant holds no valid credential accepted by this domain",
    )
