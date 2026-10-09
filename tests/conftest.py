"""Explicit endpoints for mocked unit tests; production defaults stay fail-closed."""

import pytest


@pytest.fixture(autouse=True)
def unit_test_endpoints(monkeypatch, request):
    if request.node.get_closest_marker("integration"):
        return
    monkeypatch.setenv("WARD_XRPL_URL", "https://s.altnet.rippletest.net:51234/")
    monkeypatch.setenv("WARD_XRPL_WS", "wss://s.altnet.rippletest.net:51233/")
    monkeypatch.setenv("WARD_NETWORK", "testnet")


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch, request):
    if request.node.get_closest_marker("integration"):
        return
    from ward import registry, settlement

    monkeypatch.setattr(registry, "_redis_registry", None)
    registry.clear_registry()
    monkeypatch.setattr(settlement, "_settlement_redis", None)
