#!/usr/bin/env python3
"""
Example: Monitor XLS-66 defaults in real-time.

Usage:
    python examples/monitor_defaults.py
"""

import asyncio
import sys
import os

# Add parent directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ward.monitor import XLS66Monitor, DefaultEvent


async def main():
    """Run the default monitor."""
    
    # Use testnet for demo
    monitor = XLS66Monitor(
        websocket_url="wss://s.altnet.rippletest.net:51233"
    )
    
    # Register callback for defaults
    @monitor.on_default
    async def handle_default(event: DefaultEvent):
        print("\n" + "="*60)
        print("🚨 DEFAULT DETECTED!")
        print("="*60)
        print(f"Loan ID: {event.loan.loan_id}")
        print(f"Borrower: {event.loan.borrower}")
        print(f"Transaction: {event.tx_hash}")
        print(f"Ledger: {event.ledger_index}")
        print()
        print(f"Default Amount:  {event.default_amount / 1_000_000:,.2f} XRP")
        print(f"First-Loss Cover: {event.default_covered / 1_000_000:,.2f} XRP")
        print(f"Vault Loss:       {event.vault_loss / 1_000_000:,.2f} XRP ⚠️")
        print()
        print(f"Vault ID: {event.vault.vault_id}")
        print(f"Share Value Before: {event.vault.share_value:.6f} XRP")
        print("="*60 + "\n")
    
    print("🔍 Ward Protocol - XLS-66 Default Monitor")
    print("Watching testnet for loan defaults...")
    print("Press Ctrl+C to stop\n")
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
        await monitor.stop()
        print("Monitor stopped.")


if __name__ == "__main__":
    asyncio.run(main())
