"""
ward/registry.py — Institution vault registry.

Maps institution key hashes to lists of registered vault addresses.
In-memory for now — persistent store recommended for production.

ward_signed = False — always.
"""

import asyncio
import hashlib
import json as _json
import logging
import os as _os
from collections import defaultdict
from typing import Optional

from ward.constants import VaultRegistration
from ward.primitives import WardError, validate_xrpl_address

logger = logging.getLogger(__name__)

_registry: dict[str, list[VaultRegistration]] = defaultdict(list)  # fallback only
_registry_lock = asyncio.Lock()

# Redis-backed registry

_redis_registry = None
try:
    import redis as _redis_mod

    _redis_registry = _redis_mod.Redis.from_url(
        _os.getenv("WARD_REDIS_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    _redis_registry.ping()
except Exception as _redis_exc:
    logger.warning(
        "Redis unavailable for vault registry — falling back to in-memory (not restart-safe). "
        "Set WARD_REDIS_URL for production. Error: %s",
        _redis_exc,
    )
    _redis_registry = None

_REDIS_REG_PREFIX = "ward:registry:"

_VALID_TIERS = frozenset({"starter", "standard", "enterprise"})


def _hash_key(institution_key: str) -> str:
    """SHA-256 hash of institution key — never store raw keys."""
    return hashlib.sha256(institution_key.encode()).hexdigest()


async def register_vault(
    institution_key: str,
    vault_address: str,
    tier: str = "starter",
    label: str = "",
    ledger_time: int = 0,
) -> VaultRegistration:
    """
    Register a vault address under an institution key.
    One institution key can have multiple vault addresses.
    Raises WardError if vault_address is already registered under this key.
    """
    validate_xrpl_address(vault_address)
    if tier not in _VALID_TIERS:
        raise WardError(
            f"Invalid tier: {tier!r}. Must be one of {sorted(_VALID_TIERS)}"
        )

    key_hash = _hash_key(institution_key)

    async with _registry_lock:
        if _redis_registry is not None:
            try:
                raw = _redis_registry.get(f"{_REDIS_REG_PREFIX}{key_hash}")
                existing = _json.loads(raw) if raw else []
            except Exception:
                existing = list(_registry[key_hash])
        else:
            existing = list(_registry[key_hash])
        # shadow variable for rest of function
        _registry[key_hash] = existing  # type: ignore
        for existing_entry in existing:
            if existing_entry["vault_address"] == vault_address:
                raise WardError(
                    f"Vault {vault_address} already registered under this institution key"
                )

        entry: VaultRegistration = {
            "vault_address": vault_address,
            "institution_key_hash": key_hash,
            "registered_at": ledger_time,
            "tier": tier,
            "label": label or vault_address[:8] + "...",
        }
        _registry[key_hash].append(entry)
        if _redis_registry is not None:
            try:
                _redis_registry.set(
                    f"{_REDIS_REG_PREFIX}{key_hash}",
                    _json.dumps(_registry[key_hash]),
                )
            except Exception:
                pass
        logger.info(
            "Vault registered: %s (tier=%s, institution=%s...)",
            vault_address,
            tier,
            key_hash[:8],
        )
        return entry


async def get_vaults(institution_key: str) -> list[VaultRegistration]:
    """Return all vault registrations for an institution key."""
    key_hash = _hash_key(institution_key)
    async with _registry_lock:
        return list(_registry.get(key_hash, []))


async def get_vault(
    institution_key: str,
    vault_address: str,
) -> Optional[VaultRegistration]:
    """Return a specific vault registration, or None if not found."""
    vaults = await get_vaults(institution_key)
    for v in vaults:
        if v["vault_address"] == vault_address:
            return v
    return None


async def deregister_vault(
    institution_key: str,
    vault_address: str,
) -> bool:
    """Remove a vault registration. Returns True if removed, False if not found."""
    key_hash = _hash_key(institution_key)
    async with _registry_lock:
        before = len(_registry[key_hash])
        _registry[key_hash] = [
            v for v in _registry[key_hash] if v["vault_address"] != vault_address
        ]
        removed = len(_registry[key_hash]) < before
        if removed:
            logger.info("Vault deregistered: %s", vault_address)
        return removed


async def list_all_institutions() -> dict[str, list[VaultRegistration]]:
    """Return full registry — admin use only."""
    async with _registry_lock:
        return dict(_registry)


def clear_registry() -> None:
    """Clear all registrations — for testing only."""
    _registry.clear()
