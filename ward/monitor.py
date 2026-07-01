"""
Ward Protocol monitor - vault and loan default monitoring.

Wraps ChainReader for polling-based monitoring of vault addresses
and XLS-66 loan defaults.
"""

import asyncio
import logging
import warnings
from typing import Callable, Dict, List, Optional

from ward.primitives import SecurityError, client_context

from .chain_reader import ChainReader

logger = logging.getLogger(__name__)


class WardMonitor:
    """
    Monitor vaults and accounts for Ward Protocol.

    Uses ChainReader for polling. For full XLS-66 default detection,
    use ward.VaultMonitor which subscribes to the XRPL WebSocket
    ledger stream with 3-ledger confirmation.

    WARNING: This class monitors vault balance changes via POLLING only
    (every poll_interval_seconds). XRPL produces a new ledger every 3-4s.
    Polling can miss events between intervals and is NOT suitable for
    production default detection.

    For XLS-66 default detection with 3-ledger WebSocket confirmation:
        from ward import VaultMonitor  # WebSocket + 3-ledger confirmation
    """

    def __init__(
        self,
        vault_addresses: Optional[List[str]] = None,
        xrpl_url: str = "wss://xrplcluster.com",
        poll_interval_seconds: float = 10.0,
    ) -> None:
        """
        Create a WardMonitor.

        Args:
            vault_addresses:        List of XRPL addresses to monitor.
            xrpl_url:               XRPL WebSocket endpoint.
            poll_interval_seconds:  Seconds between each polling cycle.
        """
        warnings.warn(
            "WardMonitor is deprecated; use ward.VaultMonitor for WebSocket-based "
            "3-ledger default detection.",
            DeprecationWarning,
            stacklevel=2,
        )
        if xrpl_url.startswith("ws://"):
            raise SecurityError(
                f"Plaintext ws:// endpoint rejected: {xrpl_url!r}. Use wss://."
            )
        self._vault_addresses: List[str] = vault_addresses or []
        self._xrpl_url = xrpl_url
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._callbacks: List[Callable] = []
        self._reader: Optional[ChainReader] = None

    def add_vault(self, address: str) -> None:
        """Add a vault address to the monitoring list."""
        if address not in self._vault_addresses:
            self._vault_addresses.append(address)

    def remove_vault(self, address: str) -> None:
        """Remove a vault address from the monitoring list."""
        if address in self._vault_addresses:
            self._vault_addresses.remove(address)

    def on_balance_change(self, callback: Callable) -> None:
        """
        Register a callback for vault balance changes.

        The callback receives (vault_address: str, balance_drops: int).
        """
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the polling monitor loop."""
        if self._running:
            return
        self._running = True
        logger.info(
            "WardMonitor starting: monitoring %d vaults every %.1fs",
            len(self._vault_addresses),
            self._poll_interval,
        )
        try:
            await self._poll_loop()
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the polling monitor loop."""
        self._running = False
        logger.info("WardMonitor stopping.")

    async def _poll_loop(self) -> None:
        """Internal polling loop."""
        prev_balances: Dict[str, int] = {}

        while self._running:
            for address in list(self._vault_addresses):
                try:
                    balance = await self._fetch_balance(address)
                    prev = prev_balances.get(address)
                    if prev is not None and balance != prev:
                        logger.info(
                            "Balance change for %s: %d -> %d drops",
                            address,
                            prev,
                            balance,
                        )
                        for cb in self._callbacks:
                            try:
                                result = cb(address, balance)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception as exc:
                                logger.error("Callback error for %s: %s", address, exc)
                    prev_balances[address] = balance
                except Exception as exc:
                    logger.warning("Failed to fetch balance for %s: %s", address, exc)

            await asyncio.sleep(self._poll_interval)

    async def _fetch_balance(self, address: str) -> int:
        """Fetch account balance in drops for a single address."""
        from xrpl.asyncio.clients import AsyncJsonRpcClient
        from xrpl.models import AccountInfo

        async with client_context(
            AsyncJsonRpcClient(self._xrpl_url.replace("wss://", "https://"))
        ) as client:
            resp = await client.request(
                AccountInfo(account=address, ledger_index="validated")
            )
            if not resp.is_successful():
                raise RuntimeError(f"AccountInfo failed for {address}: {resp.result}")
            return int(resp.result["account_data"]["Balance"])
