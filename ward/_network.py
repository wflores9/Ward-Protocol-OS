"""
Ward Protocol — Network configuration guard (B1 mainnet readiness).

Reads WARD_XRPL_URL, WARD_XRPL_WS, WARD_NETWORK from the process environment.
All six core modules use get_xrpl_url() / get_xrpl_ws() instead of hardcoded
Altnet defaults; they raise ConfigurationError at construction time if the env
vars are absent or inconsistent.

WARD_NETWORK guard
------------------
When WARD_NETWORK is set to 'mainnet' or 'testnet', every URL — whether
sourced from env or passed explicitly — must resolve to the declared network.
Mismatch is a hard ConfigurationError (not a warning) so misrouted production
traffic fails loud and early rather than silently targeting the wrong ledger.

Starter scripts and demo code intentionally pass explicit Altnet URLs; they
set WARD_NETWORK=testnet (or leave it unset) to document intent.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from ward.primitives import ConfigurationError

# Hosts that classify as mainnet XRPL endpoints.
_MAINNET_HOSTS: frozenset = frozenset(
    {
        "xrplcluster.com",
        "s1.ripple.com",
        "s2.ripple.com",
    }
)

# Hosts that classify as testnet/devnet XRPL endpoints.
_TESTNET_HOSTS: frozenset = frozenset(
    {
        "s.altnet.rippletest.net",
        "s.devnet.rippletest.net",
        "testnet.xrpl-labs.com",
    }
)

_VALID_NETWORKS = frozenset({"mainnet", "testnet"})


def _classify_host(url: str) -> str:
    """Return 'mainnet', 'testnet', or 'unknown' based on the URL's hostname."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "unknown"
    if host in _MAINNET_HOSTS:
        return "mainnet"
    if host in _TESTNET_HOSTS:
        return "testnet"
    return "unknown"


def _check_network_match(url: str, env_var: str) -> None:
    """
    If WARD_NETWORK is set, verify the URL resolves to that network.
    Raises ConfigurationError on mismatch or invalid WARD_NETWORK value.
    """
    ward_network = os.environ.get("WARD_NETWORK", "").strip().lower()
    if not ward_network:
        return  # Guard is opt-in — no WARD_NETWORK means no check.
    if ward_network not in _VALID_NETWORKS:
        raise ConfigurationError(
            f"WARD_NETWORK={ward_network!r} is invalid; must be 'mainnet' or 'testnet'. "
            "Unset WARD_NETWORK to disable the check."
        )
    url_network = _classify_host(url)
    if url_network == "unknown":
        return  # Non-standard endpoint — operator knows what they are doing.
    if url_network != ward_network:
        raise ConfigurationError(
            f"WARD_NETWORK={ward_network!r} but {env_var} resolves to a "
            f"{url_network!r} endpoint: {url!r}. "
            f"Use a {ward_network} endpoint or update WARD_NETWORK."
        )


def get_xrpl_url() -> str:
    """
    Return the XRPL JSON-RPC URL from the WARD_XRPL_URL environment variable.

    Raises ConfigurationError if:
    - WARD_XRPL_URL is not set or empty.
    - WARD_NETWORK is set and the URL resolves to a different network.

    Mainnet:  export WARD_XRPL_URL=https://xrplcluster.com/   WARD_NETWORK=mainnet
    Testnet:  export WARD_XRPL_URL=https://s.altnet.rippletest.net:51234/  WARD_NETWORK=testnet
    """
    url = os.environ.get("WARD_XRPL_URL", "").strip()
    if not url:
        raise ConfigurationError(
            "WARD_XRPL_URL is not set. Ward requires an explicit XRPL JSON-RPC endpoint.\n"
            "  Mainnet: export WARD_XRPL_URL=https://xrplcluster.com/   WARD_NETWORK=mainnet\n"
            "  Testnet: export WARD_XRPL_URL=https://s.altnet.rippletest.net:51234/  WARD_NETWORK=testnet"
        )
    _check_network_match(url, "WARD_XRPL_URL")
    return url


def get_xrpl_ws() -> str:
    """
    Return the XRPL WebSocket URL from the WARD_XRPL_WS environment variable.

    Raises ConfigurationError if:
    - WARD_XRPL_WS is not set or empty.
    - WARD_NETWORK is set and the URL resolves to a different network.

    Mainnet:  export WARD_XRPL_WS=wss://xrplcluster.com/   WARD_NETWORK=mainnet
    Testnet:  export WARD_XRPL_WS=wss://s.altnet.rippletest.net:51233/  WARD_NETWORK=testnet
    """
    ws = os.environ.get("WARD_XRPL_WS", "").strip()
    if not ws:
        raise ConfigurationError(
            "WARD_XRPL_WS is not set. Ward requires an explicit XRPL WebSocket endpoint.\n"
            "  Mainnet: export WARD_XRPL_WS=wss://xrplcluster.com/   WARD_NETWORK=mainnet\n"
            "  Testnet: export WARD_XRPL_WS=wss://s.altnet.rippletest.net:51233/  WARD_NETWORK=testnet"
        )
    _check_network_match(ws, "WARD_XRPL_WS")
    return ws


def validate_url_network_match(url: str, param_name: str = "url") -> None:
    """
    Check an explicitly-provided URL against WARD_NETWORK if set.
    Call this for every URL passed directly to a Ward constructor so that
    a WARD_NETWORK=mainnet guard catches accidental testnet URLs even when
    the caller supplies an explicit override.
    """
    _check_network_match(url, param_name)
