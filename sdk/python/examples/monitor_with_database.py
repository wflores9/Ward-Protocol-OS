#!/usr/bin/env python3
"""
Example: Monitor XLS-66 defaults with PostgreSQL storage.

Usage:
    # Set database connection
    export DATABASE_URL="postgresql://ward:ward_secure_password_change_me@localhost/ward_protocol"
    
    # Run monitor
    python3 examples/monitor_with_database.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ward.monitor import XLS66Monitor, DefaultEvent


async def main():
    """Run the default monitor with database storage."""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("⚠️  WARNING: DATABASE_URL not set - running without database storage")
        print("Set it with: export DATABASE_URL='postgresql://user:pass@localhost/ward_protocol'")
        print()
    
    # Create monitor (testnet + database)
    monitor = XLS66Monitor(
        websocket_url="wss://s.altnet.rippletest.net:51233",
        database_url=database_url
    )
    
    # Register callback for defaults
    @monitor.on_default
    async def handle_default(event: DefaultEvent):
        print("\n" + "="*70)
        print("🚨 DEFAULT DETECTED & STORED IN DATABASE!")
        print("="*70)
        print(f"Loan ID:          {event.loan.loan_id}")
        print(f"Borrower:         {event.loan.borrower}")
        print(f"LoanBroker:       {event.loan_broker.loan_broker_id}")
        print(f"Vault:            {event.vault.vault_id}")
        print()
        print(f"Default Amount:   {event.default_amount / 1_000_000:,.2f} XRP")
        print(f"First-Loss Cover: {event.default_covered / 1_000_000:,.2f} XRP")
        print(f"Vault Loss:       {event.vault_loss / 1_000_000:,.2f} XRP ⚠️")
        print()
        print(f"Transaction:      {event.tx_hash}")
        print(f"Ledger:           {event.ledger_index}")
        print(f"Detected:         {event.detected_at}")
        print()
        
        # Show vault impact
        share_value_before = event.vault.share_value
        loss_pct = (event.vault_loss / event.vault.assets_total) * 100
        print(f"Vault Impact:")
        print(f"  - Share Value Before: {share_value_before:.6f} XRP")
        print(f"  - Loss Percentage:    {loss_pct:.2f}%")
        print("="*70 + "\n")
    
    print("🔍 Ward Protocol - XLS-66 Default Monitor")
    print("="*70)
    if database_url:
        print("✅ Database: ENABLED")
        print(f"   Connection: {database_url.split('@')[1]}")
    else:
        print("⚠️  Database: DISABLED (events will not be stored)")
    print("🌐 Network: Testnet")
    print("👀 Watching for loan defaults...")
    print("📊 Events will be logged to PostgreSQL")
    print()
    print("Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping monitor...")
        await monitor.stop()
        print("✅ Monitor stopped.")
        
        # Show stats if database enabled
        if monitor.db:
            print("\n📊 Database Statistics:")
            try:
                events = await monitor.db.get_default_events(limit=5)
                print(f"   Total Events Logged: {len(events)}")
                if events:
                    print(f"   Latest Event: {events[0]['detected_at']}")
            except Exception as e:
                print(f"   Error reading stats: {e}")


if __name__ == "__main__":
    asyncio.run(main())
