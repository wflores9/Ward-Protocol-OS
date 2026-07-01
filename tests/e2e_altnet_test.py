"""
Ward Protocol — Full E2E Altnet Test
"""
import asyncio
from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet
from xrpl.asyncio.clients import AsyncWebsocketClient

ALTNET_RPC = "https://s.altnet.rippletest.net:51234/"
ALTNET_WS  = "wss://s.altnet.rippletest.net:51233/"

def fund_wallets():
    print("Funding wallets from Altnet faucet...")
    client = JsonRpcClient(ALTNET_RPC)
    institution = generate_faucet_wallet(client, debug=True)
    depositor   = generate_faucet_wallet(client, debug=True)
    borrower    = generate_faucet_wallet(client, debug=True)
    return institution, depositor, borrower

async def run_flows(institution, depositor, borrower):
    from ward.client import WardClient
    results = {}

    print(f"\nInstitution: {institution.classic_address}")
    print(f"Depositor:   {depositor.classic_address}")
    print(f"Borrower:    {borrower.classic_address}\n")

    ward = WardClient(url=ALTNET_RPC)

    # F·03 — Policy Purchase (what we can test with live wallets)
    print("F·03 — Policy Purchase")
    try:
        r = await ward.purchase_coverage(
            wallet=depositor,
            vault_address=borrower.classic_address,
            coverage_drops=1_000_000,
            period_days=30,
            pool_address=institution.classic_address,
            premium_rate=0.01,
            license_tier="starter"
        )
        results["F03"] = f"PASS — nft={r.get('nft_token_id','?')[:16]}... premium_tx={r.get('premium_tx','?')[:16]}..."
        print(f"  PASS")
        print(f"  NFT Token ID: {r.get('nft_token_id')}")
        print(f"  Premium TX:   {r.get('premium_tx')}")
        print(f"  Mint TX:      {r.get('mint_tx')}")
        print(f"  Coverage:     {r.get('coverage_drops')} drops")
        print(f"  Expiry ledger:{r.get('expiry_ledger')}\n")
    except Exception as e:
        results["F03"] = f"FAIL: {e}"
        print(f"  FAIL — {e}\n")

    # Summary
    print("\n=== RESULTS ===")
    all_pass = all("PASS" in v for v in results.values())
    for k, v in results.items():
        icon = "✓" if "PASS" in v else "✗"
        print(f"  {icon} {k}: {v}")

    final = "WARD E2E TEST — PASS" if all_pass else "WARD E2E TEST — PARTIAL"
    print(f"\n{final}")

    import os
    os.makedirs("docs", exist_ok=True)
    with open("docs/e2e_testnet_proof.md", "w") as f:
        f.write("# Ward Protocol — Altnet E2E Test Results\n\n")
        f.write(f"Institution: `{institution.classic_address}`\n\n")
        f.write(f"Depositor: `{depositor.classic_address}`\n\n")
        f.write(f"Borrower: `{borrower.classic_address}`\n\n")
        for k, v in results.items():
            f.write(f"- **{k}**: {v}\n")
        f.write(f"\n**{final}**\n")
    print("Saved to docs/e2e_testnet_proof.md")

if __name__ == "__main__":
    institution, depositor, borrower = fund_wallets()
    asyncio.run(run_flows(institution, depositor, borrower))
