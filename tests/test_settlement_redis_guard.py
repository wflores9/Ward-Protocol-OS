"""B3: WARD_REQUIRE_REDIS guard — settlement must fail fast when Redis
is required but unavailable, and fall back safely when it is not required.

These tests reload ward.settlement to re-run its module-level Redis init
under different environments. The restore_settlement_modules fixture
snapshots and restores sys.modules so this surgery does not leak module
state into the rest of the suite (which would break tests that imported
ward.settlement earlier).
"""
import sys

import pytest


@pytest.fixture
def restore_settlement_modules():
    """Snapshot ward / ward.settlement, then restore them after the test so
    the reload performed below leaves the import graph exactly as found."""
    keys = ("ward.settlement", "ward")
    saved = {k: sys.modules.get(k) for k in keys}
    try:
        yield
    finally:
        for k in keys:
            sys.modules.pop(k, None)
        for k, mod in saved.items():
            if mod is not None:
                sys.modules[k] = mod
        # Ensure a clean, real module object is present for later tests.
        import ward.settlement  # noqa: F401


def _reload_settlement():
    """Drop cached modules so the module-level Redis init re-runs under the
    current environment, and return the freshly imported module."""
    for mod in ("ward.settlement", "ward"):
        sys.modules.pop(mod, None)
    import ward.settlement as settlement
    return settlement


def test_require_redis_raises_when_unavailable(monkeypatch, restore_settlement_modules):
    """WARD_REQUIRE_REDIS=true + unreachable Redis -> ConfigurationError."""
    from ward.primitives import ConfigurationError

    # Point at a port nothing is listening on, and require Redis.
    monkeypatch.setenv("WARD_REQUIRE_REDIS", "true")
    monkeypatch.setenv("WARD_REDIS_URL", "redis://localhost:6390/0")

    with pytest.raises(ConfigurationError) as exc_info:
        _reload_settlement()

    assert "WARD_REQUIRE_REDIS" in str(exc_info.value)


def test_fallback_when_not_required(monkeypatch, restore_settlement_modules):
    """No WARD_REQUIRE_REDIS + unreachable Redis -> falls back, no raise."""
    monkeypatch.delenv("WARD_REQUIRE_REDIS", raising=False)
    monkeypatch.setenv("WARD_REDIS_URL", "redis://localhost:6390/0")

    settlement = _reload_settlement()  # must not raise
    assert settlement._settlement_redis is None
