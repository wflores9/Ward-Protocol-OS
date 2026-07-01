"""XLS-70 mainnet proof: Ward verifies a real, accepted Credential on
live XRPL mainnet. Read-only. ward_signed = False.
"""
import asyncio

from xrpl.asyncio.clients import AsyncJsonRpcClient

from ward.credentials import verify_xls70_credential

MAINNET_URL = "https://xrplcluster.com/"

# Real mainnet credential: issuer rGKMDUd... issued a KYC (4B5943) credential
# to subject rUujgL52..., with lsfAccepted set.
ISSUER = "rGKMDUdmquUCvoXxhcJSttnVnr2NYc9fYi"
SUBJECT = "rUujgL52fMEp5zf9bbYH1t5u52RPT1jtWa"
CRED_TYPE = "4B5943"  # "KYC"


async def main():
    client = AsyncJsonRpcClient(MAINNET_URL)
    print("=" * 70)
    print("WARD PROTOCOL — XLS-70 MAINNET CREDENTIAL PROOF")
    print("=" * 70)
    print(f"Network : XRPL mainnet ({MAINNET_URL})")
    print(f"Subject : {SUBJECT}")
    print(f"Issuer  : {ISSUER}")
    print(f"Type    : {CRED_TYPE} (KYC)")
    print()

    # Ward verifies the subject holds a valid accepted credential from the issuer.
    result = await verify_xls70_credential(client, SUBJECT, ISSUER, CRED_TYPE)
    print(f"valid   : {result.valid}")
    print(f"reason  : {result.reason or '(valid — accepted, unexpired)'}")
    print()
    print("=" * 70)
    print("ward_signed = False  |  read-only  |  no transactions submitted")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
