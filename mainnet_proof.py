"""Mainnet proof: run Ward's XLS-80 verifier against a real, live
PermissionedDomain object on XRPL mainnet. Read-only. ward_signed = False.
"""
import asyncio

from xrpl.asyncio.clients import AsyncJsonRpcClient

from ward.credentials import verify_xls80_domain_membership, verify_xls70_credential

MAINNET_URL = "https://xrplcluster.com/"
DOMAIN_ID = "3125689BD765DA18AF4A9250F8BC96D1D5355C73044FD13A5D7682597D3722A8"
DOMAIN_OWNER = "rGKMDUdmquUCvoXxhcJSttnVnr2NYc9fYi"
AN_ISSUER = "rUujgL52fMEp5zf9bbYH1t5u52RPT1jtWa"
CRED_TYPE = "4B5943"


async def main():
    client = AsyncJsonRpcClient(MAINNET_URL)
    print("=" * 70)
    print("WARD PROTOCOL — XLS-80 MAINNET VERIFICATION PROOF")
    print("=" * 70)
    print(f"Network:   XRPL mainnet ({MAINNET_URL})")
    print(f"Domain ID: {DOMAIN_ID}")
    print(f"Owner:     {DOMAIN_OWNER}")
    print()

    print("[1] verify_xls80_domain_membership(owner) against live mainnet domain")
    result = await verify_xls80_domain_membership(client, DOMAIN_OWNER, DOMAIN_ID)
    print(f"    member            : {result.member}")
    print(f"    reason            : {result.reason or '(member)'}")
    print(f"    matched_issuer    : {result.matched_issuer or '(none)'}")
    print(f"    matched_cred_type : {result.matched_credential_type or '(none)'}")
    print()

    print("[2] verify_xls70_credential(owner, accepted_issuer) on mainnet")
    cred = await verify_xls70_credential(client, DOMAIN_OWNER, AN_ISSUER, CRED_TYPE)
    print(f"    valid             : {cred.valid}")
    print(f"    reason            : {cred.reason or '(valid)'}")
    print()

    print("=" * 70)
    print("ward_signed = False  |  reads only  |  no transactions submitted")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
