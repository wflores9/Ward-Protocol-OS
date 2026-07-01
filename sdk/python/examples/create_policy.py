#!/usr/bin/env python3
"""
Example: Create insurance policy with NFT certificate.

Usage:
    export DATABASE_URL="postgresql://ward:ward_secure_password_change_me@localhost/ward_protocol"
    export WARD_WALLET_SEED="sXXXXXXXXXXXXXXXXXXXXXXXXXX"
    
    python3 examples/create_policy.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.wallet import Wallet

from ward.policy import PolicyManager, PolicyRequest
from ward.database import WardDatabase


async def main():
    """Create example insurance policy."""
    
    database_url = os.getenv('DATABASE_URL')
    wallet_seed = os.getenv('WARD_WALLET_SEED')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL required")
        return
    
    if not wallet_seed:
        print("⚠️  WARNING: WARD_WALLET_SEED not set")
        print("   Using testnet faucet wallet (for demo only)")
        # For demo, we'll generate a wallet
        wallet = Wallet.create()
        print(f"   Generated wallet: {wallet.address}")
    else:
        wallet = Wallet.from_seed(wallet_seed)
    
    # Connect to testnet
    client = AsyncWebsocketClient("wss://s.altnet.rippletest.net:51233")
    await client.open()
    
    # Connect to database
    db = WardDatabase(database_url)
    await db.connect()
    
    # Create policy manager
    pool_premium_account = "rPremiumCollectorAddress"  # Placeholder
    policy_manager = PolicyManager(
        client=client,
        wallet=wallet,
        database=db,
        pool_premium_account=pool_premium_account
    )
    
    print("🏦 Ward Protocol - Policy Creator")
    print("="*70)
    print(f"Issuer:  {wallet.address}")
    print(f"Network: Testnet")
    print("="*70 + "\n")
    
    # Example policy request
    request = PolicyRequest(
        vault_id="2DE64CA41250EF3CB7D2B127D6CEC31F747492CAE2BD1628CA02EA1FFE7475B3",
        insured_address="rInsuredDepositorAddress",  # Placeholder
        coverage_amount=50_000_000_000,  # 50,000 XRP
        term_days=90,
        pool_id="3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A"
    )
    
    print("📋 Policy Request:")
    print(f"   Vault:    {request.vault_id[:16]}...")
    print(f"   Insured:  {request.insured_address}")
    print(f"   Coverage: {request.coverage_amount / 1_000_000:,.0f} XRP")
    print(f"   Term:     {request.term_days} days")
    print()
    
    # Calculate premium (simplified - 2% of coverage)
    premium_rate = 0.02
    premium_amount = int(request.coverage_amount * premium_rate)
    
    print(f"💰 Premium: {premium_amount / 1_000_000:,.2f} XRP ({premium_rate*100}%)")
    print()
    print("🔨 Creating policy...")
    print()
    
    try:
        policy = await policy_manager.create_policy(
            request=request,
            premium_amount=premium_amount
        )
        
        print("✅ POLICY CREATED!")
        print("="*70)
        print(f"Policy ID:   {policy.policy_id}")
        print(f"NFT Token:   {policy.nft_token_id}")
        print(f"Coverage:    {policy.coverage_amount / 1_000_000:,.0f} XRP")
        print(f"Premium:     {policy.premium_paid / 1_000_000:,.2f} XRP")
        print(f"Start:       {policy.coverage_start}")
        print(f"End:         {policy.coverage_end}")
        print(f"Status:      {policy.status}")
        print("="*70)
        
    except Exception as e:
        print(f"❌ Error creating policy: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    await client.close()
    await db.disconnect()
    
    print("\n✅ Done")


if __name__ == "__main__":
    asyncio.run(main())
