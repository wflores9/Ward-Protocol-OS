# Ward Protocol — Mainnet Readiness Assessment

**Date:** 2026-06-10  
**Version:** 0.2.6  
**Status:** NOT READY FOR MAINNET — 4 blockers open

---

## Blocker Summary

| # | Blocker | File(s) | Status |
|---|---------|---------|--------|
| B1 | Testnet URL was the default for all six core modules | validator.py, resolver.py, settlement.py, pool.py, vault_monitor.py, client.py | **CLOSED** — `ward/_network.py` + env guard (see below) |
| B2 | Rate limiter is in-memory — bypassed across instances or restarts | primitives.py | **OPEN** — Migrate to Redis-backed sliding window |
| B3 | Settlement lock falls back to in-memory on Redis unavail | settlement.py | **OPEN** — Make Redis mandatory in production |
| B4 | Coverage registry is per-instance in-memory | pool.py | **OPEN** — Evaluate on-chain read vs Redis-backed registry |

---

## B1 — Testnet URL Defaults — CLOSED ✓

### What Was Fixed

New module `ward/_network.py` provides `get_xrpl_url()`, `get_xrpl_ws()`, and `validate_url_network_match()`. All six core constructors now default to `None` and call `get_xrpl_url()` / `get_xrpl_ws()` when no explicit URL is provided. `ConfigurationError` (new, subclass of `WardError`) is raised at construction time if:

1. `WARD_XRPL_URL` is not set (RPC modules).
2. `WARD_XRPL_WS` is not set (VaultMonitor).
3. `WARD_NETWORK` is set to `mainnet` or `testnet` and the URL resolves to the other network — mismatch is a hard failure regardless of whether the URL came from the env var or an explicit constructor argument.

```bash
# Mainnet deployment
export WARD_XRPL_URL=https://xrplcluster.com/
export WARD_XRPL_WS=wss://xrplcluster.com/
export WARD_NETWORK=mainnet

# Testnet / CI
export WARD_XRPL_URL=https://s.altnet.rippletest.net:51234/
export WARD_XRPL_WS=wss://s.altnet.rippletest.net:51233/
export WARD_NETWORK=testnet
```

`DEFAULT_TESTNET_URL` / `DEFAULT_TESTNET_WS` constants are retained in `ward/constants.py` for use by starter scripts and integration tests — they are no longer used as constructor defaults.

### Starter / Demo Files (Intentional Testnet Config)

Files in `starter/python/`, `starter/typescript/`, and the dashboard demo intentionally target Altnet by passing explicit URLs. This is by design — they are learning examples, not production deployments. Each file uses `os.getenv("XRPL_JSON_RPC_URL", DEFAULT_TESTNET_URL)` so operators can override via env var.

### Test Coverage

13 new tests in `TestNetworkConfig` (`test_ward.py`) cover:
- Missing `WARD_XRPL_URL` / `WARD_XRPL_WS` → `ConfigurationError` for all 6 classes
- Testnet URL + `WARD_NETWORK=mainnet` → `ConfigurationError`
- Mainnet URL + `WARD_NETWORK=testnet` → `ConfigurationError`
- Explicit mainnet URL override while `WARD_NETWORK=testnet` → `ConfigurationError`
- Invalid `WARD_NETWORK` value → `ConfigurationError`
- Mainnet URL + `WARD_NETWORK=mainnet` → accepted
- Testnet URL + no `WARD_NETWORK` → accepted (guard is opt-in)

---

## B2 — In-Memory Rate Limiter

### Current State

```python
# ward/primitives.py:239-296
_rate_limit_lock: threading.Lock = threading.Lock()
_rate_limit_windows: dict = {}  # nft_token_id -> deque[float]
```

The sliding-window rate limiter (≤3 claims/NFT/300s) lives entirely in this dict. The `threading.Lock` is not multiprocessing-safe.

### Risk

- Multi-process deployments (gunicorn workers, Railway instances) each maintain separate windows — the limit is effectively multiplied by worker count.
- A process restart resets all windows — a burst of claims immediately after a restart bypasses the limit entirely.
- An attacker who triggers a worker restart (OOM, deploy) gets a window reset.

### Remediation

Migrate `check_rate_limit()` and `record_rate_limit_call()` to Redis with `ZADD` / `ZRANGEBYSCORE` / `ZREMRANGEBYSCORE` pattern. TTL on the sorted set ensures cleanup. This is a ~50-line change to `ward/primitives.py`.

---

## B3 — Settlement Lock Redis Dependency

### Current State

```python
# ward/settlement.py:46-58
_settlement_redis = None
try:
    import redis as _redis
    _settlement_redis = _redis.Redis.from_url(...)
    _settlement_redis.ping()
except Exception as _redis_exc:
    logger.warning("Redis unavailable for settlement locks...")
    _settlement_redis = None
```

When Redis is unavailable, settlement falls back to a per-instance `threading.Lock`. The `_SETTLEMENT_LOCK_TTL = 3600` (1 hour) is enforced only in Redis mode.

### Risk

Without Redis, two concurrent settlement requests for the same claim on different workers can both pass the lock check and attempt double-settlement. The XRPL ledger's atomic operations provide the final safety net (the second NFTokenBurn will fail), but this creates a failed transaction that wastes drops and requires investigation.

### Remediation

Add `WARD_REQUIRE_REDIS` environment variable. When set, raise `ConfigurationError` at module import if Redis is unavailable. Recommended for all production deployments.

---

## B4 — In-Memory Coverage Registry

### Current State

```python
# ward/pool.py:88
self._coverage_registry: Dict[str, int] = {}
```

`PoolHealthMonitor` maintains per-instance coverage state. The `set_coverage()` and `clear_coverage()` calls (invoked by the API on policy purchase and settlement) only update the local instance's registry.

### Risk

On multi-instance deployments, pool-level coverage checks may miss or double-count active policies depending on which instance handled the purchase vs. the claim.

### Remediation

The existing `ward/coverage.py` module provides an on-chain coverage registry that reads from XRPL. Evaluate whether `PoolHealthMonitor._coverage_registry` can be replaced by direct on-chain reads, or migrate to Redis-backed registry consistent with keys/registry patterns.

---

## Non-Blocking Gaps

### ALLOWED_WS_URLS includes Altnet

```python
# ward/constants.py:140
ALLOWED_WS_URLS: frozenset = frozenset({
    "wss://s.altnet.rippletest.net:51233/",  # testnet — must be audited at deploy time
    "wss://xrplcluster.com/",
    "wss://s1.ripple.com/",
    "wss://s2.ripple.com/",
})
```

The Rust `ALLOWED_WS_URLS` (monitor.rs) mirrors this. Including Altnet is correct for testnet support. For mainnet, consider a separate `MAINNET_ALLOWED_WS_URLS` constant and validate against it when `WARD_ENV=production`.

### submit_with_retry() Still Present

`ward/primitives.py:459` — function body exists and is callable despite being marked DEPRECATED. Now emits `DeprecationWarning`. Must be removed before mainnet GA.

### ward_client.py (Legacy Root File)

`/home/user/ward-protocol/ward_client.py` exists at the repo root. This appears to be a pre-modularization legacy file. It should be audited and either removed or marked explicitly as deprecated.

### XRPL Reserve Constants

```python
XRPL_BASE_RESERVE_DROPS = 20_000_000  # 20 XRP
XRPL_OWNER_RESERVE_DROPS = 2_000_000  # 2 XRP per owned object
```

These are hardcoded in `ward/constants.py`. XRPL reserve requirements can change via amendment. For mainnet, consider reading these from the `server_info` RPC response and caching with a TTL, or at minimum adding a startup validation that compares the constant against the live ledger.

---

## Mainnet Go-Live Checklist

- [x] **B1**: Testnet defaults removed; `WARD_XRPL_URL` / `WARD_XRPL_WS` / `WARD_NETWORK` required
- [ ] **B2**: Migrate rate limiter to Redis ZADD/ZRANGEBYSCORE
- [ ] **B3**: Add `WARD_REQUIRE_REDIS=true` guard; prohibit in-memory fallback in prod
- [ ] **B4**: Evaluate on-chain coverage read vs. Redis-backed registry
- [ ] Remove `submit_with_retry()` function body (keep stub that raises immediately)
- [ ] Audit and remove or archive `ward_client.py` root-level legacy file
- [ ] Add preflight check script that validates all URLs point to mainnet
- [ ] Confirm XRPL reserve constants match current live mainnet `server_info`
- [ ] Ensure Redis is provisioned and `WARD_REDIS_URL` is set in all production environments
- [ ] All 634 tests (Python / 22 Rust / 53 TypeScript) green on mainnet network config
- [ ] Load test multi-instance deployment with Redis to verify rate limiter correctness
