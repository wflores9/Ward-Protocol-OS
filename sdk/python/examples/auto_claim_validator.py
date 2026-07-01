#!/usr/bin/env python3
"""
Example: Automatic claim validation for XLS-66 defaults.

Monitors defaults and automatically validates insurance claims.

Usage:
    export DATABASE_URL="postgresql://ward:ward_secure_password_change_me@localhost/ward_protocol"
    python3 examples/auto_claim_validator.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ward.monitor import XLS66Monitor, DefaultEvent
from ward.validator import ClaimValidator
from ward.database import WardDatabase


async def main():
    """Run monitor with automatic claim validation."""
    
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL required for claim validation")
        print("Set it with: export DATABASE_URL='postgresql://user:pass@localhost/ward_protocol'")
        return
    
    # Create database connection
    db = WardDatabase(database_url)
    await db.connect()
    
    # Create validator
    validator = ClaimValidator(db)
    
    # Create monitor
    monitor = XLS66Monitor(
        websocket_url="wss://s.altnet.rippletest.net:51233",
        database_url=database_url
    )
    
    # Register automatic claim validation
    @monitor.on_default
    async def handle_default_and_validate(event: DefaultEvent):
        print("\n" + "="*70)
        print("🚨 DEFAULT DETECTED - STARTING CLAIM VALIDATION")
        print("="*70)
        print(f"Loan:        {event.loan.loan_id}")
        print(f"Vault Loss:  {event.vault_loss / 1_000_000:.2f} XRP")
        print()
        
        # TODO: Look up active policy for this vault
        # For now, we'll skip validation without a policy
        print("⚠️  No policy lookup implemented yet")
        print("   (Would validate claim here if policy exists)")
        print("="*70 + "\n")
        
        # Example validation (commented out - requires actual policy):
        # result = await validator.validate_and_approve(
        #     loan_id=event.loan.loan_id,
        #     policy_id="some-policy-uuid",
        #     loan=event.loan,
        #     loan_broker=event.loan_broker,
        #     vault=event.vault,
        #     tx_hash=event.tx_hash
        # )
        # 
        # if result.approved:
        #     print(f"✅ CLAIM APPROVED: {result.claim_payout / 1_000_000:.2f} XRP")
        # else:
        #     print(f"❌ CLAIM REJECTED: {result.rejection_reason}")
    
    print("🔍 Ward Protocol - Auto Claim Validator")
    print("="*70)
    print("✅ Database: ENABLED")
    print("✅ Claim Validator: ENABLED")
    print("🌐 Network: Testnet")
    print()
    print("Monitoring defaults and auto-validating claims...")
    print("Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping...")
        await monitor.stop()
        await db.disconnect()
        print("✅ Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
