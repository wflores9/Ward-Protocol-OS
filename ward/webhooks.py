"""
ward/webhooks.py — Webhook notification system.

Fires HMAC-signed HTTP callbacks when vault health thresholds are crossed.

ward_signed = False — always.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request as _URLRequest
from urllib.request import urlopen

from ward.primitives import WardError, validate_xrpl_address

logger = logging.getLogger("ward.webhooks")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

THRESHOLD_WARNING = 2.0
THRESHOLD_ELEVATED = 1.75
THRESHOLD_CRITICAL = 1.5

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Enums / data classes
# ---------------------------------------------------------------------------


class WebhookEvent(str, Enum):
    HEALTH_WARNING = "health.warning"
    HEALTH_ELEVATED = "health.elevated"
    HEALTH_CRITICAL = "health.critical"
    DEFAULT_DETECTED = "default.detected"
    DEFAULT_RESOLVED = "default.resolved"
    CLAIM_FILED = "claim.filed"
    CLAIM_SETTLED = "claim.settled"


@dataclass
class WebhookConfig:
    url: str
    vault_address: str
    secret: str = ""
    events: List[WebhookEvent] = field(default_factory=list)  # empty = all events


@dataclass
class WebhookPayload:
    event: WebhookEvent
    vault_address: str
    health_ratio: Optional[float]
    timestamp: int
    ward_signed: bool = False  # always False — invariant
    data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-memory webhook registry
# ---------------------------------------------------------------------------

_webhook_registry: Dict[str, List[WebhookConfig]] = {}
_webhook_lock = asyncio.Lock()


async def register_webhook(config: WebhookConfig) -> None:
    """Register a webhook for a vault address."""
    validate_xrpl_address(config.vault_address)
    _validate_webhook_url(config.url)
    async with _webhook_lock:
        if config.vault_address not in _webhook_registry:
            _webhook_registry[config.vault_address] = []
        _webhook_registry[config.vault_address].append(config)
    logger.info("Webhook registered: %s → %s", config.vault_address, config.url)


async def deregister_webhook(vault_address: str, url: str) -> bool:
    """Remove a webhook by vault+url. Returns True if removed."""
    async with _webhook_lock:
        if vault_address not in _webhook_registry:
            return False
        before = len(_webhook_registry[vault_address])
        _webhook_registry[vault_address] = [
            c for c in _webhook_registry[vault_address] if c.url != url
        ]
        return len(_webhook_registry[vault_address]) < before


async def get_webhooks(vault_address: str) -> List[WebhookConfig]:
    """Return all webhook configs for a vault."""
    async with _webhook_lock:
        return list(_webhook_registry.get(vault_address, []))


def clear_webhooks() -> None:
    """Clear all webhooks — testing only."""
    _webhook_registry.clear()


# ---------------------------------------------------------------------------
# Threshold detection
# ---------------------------------------------------------------------------


def determine_event(
    health_ratio: float,
    previous_ratio: Optional[float],
) -> Optional[WebhookEvent]:
    """
    Return a WebhookEvent if a threshold was crossed downward, else None.

    Downward crossings (most severe checked first):
      HEALTH_CRITICAL  — crossed below 1.5
      HEALTH_ELEVATED  — crossed below 1.75
      HEALTH_WARNING   — crossed below 2.0

    Upward recovery:
      DEFAULT_RESOLVED — crossed above 1.5
    """
    if previous_ratio is None:
        return None

    # Downward — most severe first
    if health_ratio < THRESHOLD_CRITICAL and previous_ratio >= THRESHOLD_CRITICAL:
        return WebhookEvent.HEALTH_CRITICAL
    if health_ratio < THRESHOLD_ELEVATED and previous_ratio >= THRESHOLD_ELEVATED:
        return WebhookEvent.HEALTH_ELEVATED
    if health_ratio < THRESHOLD_WARNING and previous_ratio >= THRESHOLD_WARNING:
        return WebhookEvent.HEALTH_WARNING

    # Upward recovery
    if health_ratio >= THRESHOLD_CRITICAL and previous_ratio < THRESHOLD_CRITICAL:
        return WebhookEvent.DEFAULT_RESOLVED

    return None


# ---------------------------------------------------------------------------
# Firing webhooks
# ---------------------------------------------------------------------------


async def fire_webhook(payload: WebhookPayload) -> None:
    """
    Fire webhooks for all configs matching this vault and event.
    Non-blocking — errors are logged, never raised to the caller.
    """
    configs = await get_webhooks(payload.vault_address)
    for config in configs:
        if config.events and payload.event not in config.events:
            continue
        asyncio.create_task(_post_webhook(config, payload))


async def _post_webhook(config: WebhookConfig, payload: WebhookPayload) -> None:
    """POST payload to config.url with retries and exponential backoff."""
    body = json.dumps(
        {
            "event": payload.event.value,
            "vault_address": payload.vault_address,
            "health_ratio": payload.health_ratio,
            "timestamp": payload.timestamp,
            "ward_signed": False,
            "data": payload.data,
        }
    ).encode()

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if config.secret:
        sig = hmac.new(config.secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Ward-Signature"] = f"sha256={sig}"

    for attempt in range(MAX_RETRIES):
        try:
            req = _URLRequest(config.url, data=body, headers=headers, method="POST")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: urlopen(req, timeout=10))
            logger.info("Webhook delivered: %s → %s", payload.event.value, config.url)
            return
        except Exception as exc:
            wait = 2**attempt
            logger.warning(
                "Webhook delivery failed (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                MAX_RETRIES,
                exc,
                wait,
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(wait)

    logger.error(
        "Webhook delivery gave up after %d attempts: %s", MAX_RETRIES, config.url
    )


def _validate_webhook_url(url: str) -> None:
    """URL must use https:// — plaintext HTTP rejected. Private IPs blocked (SSRF protection)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise WardError(f"Webhook URL must use https://: {url!r}")
    parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
    hostname = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise WardError(
                f"Webhook URL targets a private/internal address — blocked: {url!r}"
            )
    except (socket.gaierror, ValueError):
        pass  # Unresolvable at registration time — will fail at delivery
