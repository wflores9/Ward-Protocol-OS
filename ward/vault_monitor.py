"""
Ward Protocol — Module 2: VaultMonitor

Trustless WebSocket default detection with 3-ledger confirmation.

Fixes applied:
    #1  Extracted from ward_client.py monolith into own module.
    #3  AsyncWebsocketClient used as async context manager.
    #5  Reconnect loop with exponential backoff on disconnect.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, cast

from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.models import LedgerEntry, Subscribe

from ward._network import get_xrpl_ws, validate_url_network_match
from ward.constants import (
    ALLOWED_WS_URLS,
    DEFAULT_CONFIRM_COUNT,
    LSF_LOAN_DEFAULT,
    MONITOR_HEARTBEAT_TIMEOUT_S,
)
from ward.primitives import ValidationError, validate_xrpl_address
from ward.webhooks import (
    WebhookEvent,
    WebhookPayload,
    determine_event,
    fire_webhook,
)

logger = logging.getLogger("ward.vault_monitor")

# Anomaly detection: how many consecutive below-threshold signals = anomaly
ANOMALY_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DefaultSignal:
    """Candidate default signal — detected on-chain but not yet confirmed."""

    vault_address: str
    loan_id: str
    health_ratio: float
    ledger_index: int
    confirm_count: int = 0


@dataclass
class VerifiedDefault:
    """A default confirmed across DEFAULT_CONFIRM_COUNT ledger closes."""

    vault_address: str
    loan_id: str
    health_ratio: float
    first_ledger_index: int
    confirmed_ledger: int
    outstanding_amount: int = 0
    collateral_amount: int = 0
    loan_flags: int = 0


# ---------------------------------------------------------------------------
# VaultMonitor
# ---------------------------------------------------------------------------


class VaultMonitor:
    """
    Module 2 — Trustless WebSocket default detection.

    Subscribes to the XRPL ledger stream and monitors vault and loan-broker
    accounts. When a default signal is seen on DEFAULT_CONFIRM_COUNT
    consecutive ledger closes, the on_verified_default callbacks fire.

    Usage::

        monitor = VaultMonitor(vault_addresses=["rVaultXXX..."])

        @monitor.on_verified_default
        async def handle_default(event: VerifiedDefault):
            print(f"Default confirmed: {event.vault_address}")

        await monitor.run()
    """

    def __init__(
        self,
        vault_addresses: Optional[List[str]] = None,
        websocket_url: Optional[str] = None,
        confirm_count: int = DEFAULT_CONFIRM_COUNT,
    ) -> None:
        if websocket_url is None:
            websocket_url = get_xrpl_ws()
        else:
            validate_url_network_match(websocket_url, "websocket_url")
        # 2.7 — reject non-TLS and unknown endpoints at construction time.
        _validate_ws_url(websocket_url)

        self._ws_url = websocket_url
        self._confirm_count = confirm_count

        self._vault_addresses: Set[str] = set()
        self._broker_addresses: Set[str] = set()
        self._broker_to_vault: Dict[str, str] = {}
        self._pending: Dict[str, DefaultSignal] = {}
        self._health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._recent_signals: Dict[str, deque] = defaultdict(deque)
        self._previous_ratios: Dict[str, float] = {}
        self._default_callbacks: List[Callable] = []
        self._anomaly_callbacks: List[Callable] = []
        self._stop_event = asyncio.Event()
        self._running = False

        for addr in vault_addresses or []:
            self.add_vault(addr)

    # ------------------------------------------------------------------
    # Registration decorators
    # ------------------------------------------------------------------

    def on_verified_default(self, callback: Callable) -> Callable:
        self._default_callbacks.append(callback)
        return callback

    def on_anomaly(self, callback: Callable) -> Callable:
        self._anomaly_callbacks.append(callback)
        return callback

    # ------------------------------------------------------------------
    # Vault / broker management
    # ------------------------------------------------------------------

    def add_vault(self, address: str) -> None:
        validate_xrpl_address(address, "vault_address")
        self._vault_addresses.add(address)

    def add_loan_broker(self, address: str, vault_address: str = "") -> None:
        validate_xrpl_address(address, "loan_broker_address")
        if vault_address:
            validate_xrpl_address(vault_address, "vault_address")
        self._broker_addresses.add(address)
        if vault_address:
            self._broker_to_vault[address] = vault_address

    # ------------------------------------------------------------------
    # Run loop with reconnect (Fix #5)
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Start monitoring. Reconnects automatically on disconnect or heartbeat timeout.

        Exponential backoff: 1s, 2s, 4s, 8s … max 60s.
        Heartbeat: if no ledger_closed event arrives within
        MONITOR_HEARTBEAT_TIMEOUT_S seconds, treat as disconnect (2.15).
        """
        self._running = True
        delay = 1.0

        while self._running and not self._stop_event.is_set():
            try:
                async with AsyncWebsocketClient(self._ws_url) as client:
                    delay = 1.0  # reset on successful connect
                    await self._subscribe(client)
                    await self._run_with_heartbeat(client)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._running:
                    logger.warning(
                        "VaultMonitor disconnected (%s). Reconnecting in %.0fs.",
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)

    async def _run_with_heartbeat(self, client: AsyncWebsocketClient) -> None:
        """
        Run the message loop with a per-message heartbeat timeout (2.15).

        If no message arrives within MONITOR_HEARTBEAT_TIMEOUT_S seconds,
        raises asyncio.TimeoutError to trigger reconnect.
        """
        aiter = client.__aiter__()
        while True:
            try:
                message = await asyncio.wait_for(
                    aiter.__anext__(),
                    timeout=float(MONITOR_HEARTBEAT_TIMEOUT_S),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "VaultMonitor heartbeat timeout (%ds) — reconnecting.",
                    MONITOR_HEARTBEAT_TIMEOUT_S,
                )
                raise
            except StopAsyncIteration:
                return
            if self._stop_event.is_set():
                return
            await self._handle_message(client, message)

    async def stop(self) -> None:
        self._stop_event.set()
        self._running = False

    # ------------------------------------------------------------------
    # Internal — WebSocket subscribe
    # ------------------------------------------------------------------

    async def _subscribe(self, client: AsyncWebsocketClient) -> None:
        all_addresses = list(self._vault_addresses | self._broker_addresses)
        sub = Subscribe(accounts=all_addresses, streams=cast(Any, ["ledger"]))
        await client.send(sub)

    # ------------------------------------------------------------------
    # Internal — message dispatch
    # ------------------------------------------------------------------

    async def _handle_message(
        self,
        client: AsyncWebsocketClient,
        message: dict,
    ) -> None:
        tx_type = message.get("transaction", {}).get("TransactionType")
        if tx_type:
            await self._handle_transaction(client, message)
            return

        ledger_index = message.get("ledger_index")
        if ledger_index:
            await self._process_pending_confirmations(client, int(ledger_index))

    async def _handle_transaction(
        self,
        client: AsyncWebsocketClient,
        message: dict,
    ) -> None:
        tx = message.get("transaction", {})
        meta = message.get("meta", {})
        acct = tx.get("Account", "")

        if acct not in self._broker_addresses:
            return

        vault_address = self._broker_to_vault.get(acct, "")
        loan_id = tx.get("LoanID", tx.get("Offer", ""))
        if not loan_id:
            return

        flags = int(
            meta.get("AffectedNodes", [{}])[0].get("FinalFields", {}).get("Flags", 0)
        )
        if not (flags & LSF_LOAN_DEFAULT):
            return

        outstanding = int(
            meta.get("AffectedNodes", [{}])[0]
            .get("FinalFields", {})
            .get("PrincipalOutstanding", 0)
        )
        collateral = int(
            meta.get("AffectedNodes", [{}])[0]
            .get("FinalFields", {})
            .get("CollateralAmount", 0)
        )
        ratio = collateral / outstanding if outstanding > 0 else float("inf")

        if vault_address:
            prev_ratio = self._previous_ratios.get(vault_address)
            self._previous_ratios[vault_address] = ratio
            wh_event = determine_event(ratio, prev_ratio)
            if wh_event:
                asyncio.create_task(
                    fire_webhook(
                        WebhookPayload(
                            event=wh_event,
                            vault_address=vault_address,
                            health_ratio=ratio,
                            timestamp=int(time.time()),
                        )
                    )
                )

            self._recent_signals[vault_address].append((time.time(), ratio))
            if self._detect_anomaly(vault_address):
                await self._fire_callbacks(
                    self._anomaly_callbacks,
                    {"vault_address": vault_address, "ratio": ratio},
                )

        ledger_index = int(message.get("ledger_index", 0))

        if loan_id in self._pending:
            self._pending[loan_id].confirm_count += 1
        else:
            self._pending[loan_id] = DefaultSignal(
                vault_address=vault_address,
                loan_id=loan_id,
                health_ratio=ratio,
                ledger_index=ledger_index,
            )

    async def _process_pending_confirmations(
        self,
        client: AsyncWebsocketClient,
        current_ledger: int,
    ) -> None:
        confirmed = []
        for loan_id, signal in list(self._pending.items()):
            signal.confirm_count += 1
            if signal.confirm_count >= self._confirm_count:
                verified = await self._verify_default_on_chain(client, signal)
                if verified:
                    confirmed.append((loan_id, verified))

        for loan_id, event in confirmed:
            del self._pending[loan_id]
            await self._fire_callbacks(self._default_callbacks, event)
            if event.vault_address:
                asyncio.create_task(
                    fire_webhook(
                        WebhookPayload(
                            event=WebhookEvent.DEFAULT_DETECTED,
                            vault_address=event.vault_address,
                            health_ratio=event.health_ratio,
                            timestamp=int(time.time()),
                        )
                    )
                )

    async def _verify_default_on_chain(
        self,
        client: AsyncWebsocketClient,
        signal: DefaultSignal,
    ) -> Optional[VerifiedDefault]:
        try:
            resp = await client.request(LedgerEntry(index=signal.loan_id))
            if not resp.is_successful():
                return None
            node = resp.result.get("node", {})
            flags = int(node.get("Flags", 0))
            if not (flags & LSF_LOAN_DEFAULT):
                return None
            return VerifiedDefault(
                vault_address=signal.vault_address,
                loan_id=signal.loan_id,
                health_ratio=signal.health_ratio,
                first_ledger_index=signal.ledger_index,
                confirmed_ledger=signal.ledger_index + signal.confirm_count,
                outstanding_amount=int(node.get("PrincipalOutstanding", 0)),
                collateral_amount=int(node.get("CollateralAmount", 0)),
                loan_flags=flags,
            )
        except Exception as exc:
            logger.warning("On-chain default verification failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    def _detect_anomaly(self, vault_address: str) -> bool:
        now = time.time()
        window = 300.0  # 5-minute window
        signals = self._recent_signals[vault_address]
        # Prune expired entries
        while signals and now - signals[0][0] > window:
            signals.popleft()
        if len(signals) < ANOMALY_THRESHOLD:
            return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _fire_callbacks(callbacks: List[Callable], event: Any) -> None:
        for cb in callbacks:
            try:
                await cb(event)
            except Exception as exc:
                logger.error("Callback error: %s", exc)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _validate_ws_url(url: str) -> None:
    """
    Validate a WebSocket URL against the allow-list (attack vector 2.7).

    Rules:
      - Must use wss:// (TLS required — ws:// is rejected)
      - Must be in ALLOWED_WS_URLS

    Raises:
        ValidationError: if the URL fails either check.
    """
    if not url.startswith("wss://"):
        raise ValidationError(
            f"VaultMonitor WebSocket URL must use wss:// (TLS required): {url!r}"
        )
    if url not in ALLOWED_WS_URLS:
        raise ValidationError(
            f"VaultMonitor WebSocket URL not in allowed list: {url!r}. "
            f"Allowed: {sorted(ALLOWED_WS_URLS)}"
        )
