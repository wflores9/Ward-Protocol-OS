# Ward Protocol — Refactor History

This document records every architectural refactor to the Ward Protocol SDK,
the reasoning behind each decision, and what changed.

---

## v0.2.x — Modular Hardening Pass  (April 2026)

### Motivation

The v0.1.x SDK was a single 2,085-line file (`ward_client.py`).
After the initial testnet validation and XRPLF grant submission, a thorough
code review identified 7 structural issues that would block institutional adoption:

| # | Issue | Risk |
|---|---|---|
| #1 | Monolith — all 5 classes in one file | Impossible to audit, test, or version independently |
| #2 | `wallet: Any` typing | Caller could pass anything; no validation at boundary |
| #3 | `AsyncJsonRpcClient` stored as instance attr | Connection leaked on exception; never closed |
| #4 | Client created in `__init__`, never re-used safely | Race conditions on concurrent use |
| #5 | VaultMonitor WebSocket: no reconnect logic | Single network hiccup kills the monitor permanently |
| #6 | Bare `submit_and_wait` — no retry | `telINSUF_FEE_P`, `terRETRY` etc. would fail silently |
| #7 | `active_coverage_drops` as caller parameter | Trust boundary violation — caller could pass 0 to bypass solvency check |

### What Changed

The monolith was extracted into 7 focused modules under `ward/`:

```
ward/
├── __init__.py        Public API  (v0.2.2)
├── constants.py       Single source of truth — all magic numbers + LicenseTier
├── primitives.py      Errors, validators, crypto, submit_with_retry
├── client.py          WardClient  (Module 1)
├── vault_monitor.py   VaultMonitor  (Module 2)
├── validator.py       ClaimValidator  (Module 3)
├── settlement.py      EscrowSettlement  (Module 4)
└── pool.py            PoolHealthMonitor  (Module 5)
```

**Fix #1 — Modular split.** Each module is independently auditable, testable, and versioned.

**Fix #2 — Typed wallet.** All `wallet` parameters are now typed `xrpl.wallet.Wallet`
and validated at the call boundary by `validate_wallet()` in `primitives.py`.
Ward never stores the wallet.

**Fix #3 — Context manager client.** Every method that needs a client opens
`async with AsyncJsonRpcClient(self._url) as client:` inline. The connection
is always closed, even on exception.

**Fix #4 — No long-lived client attribute.** `self._url` is stored (a string),
not `self._client` (an open socket). This eliminates the leaked-connection class of bugs.

**Fix #5 — WebSocket reconnect.** `VaultMonitor.run()` wraps the listen loop in
exponential-backoff retry. A single disconnect no longer kills monitoring.

**Fix #6 — Retry logic.** All XRPL submissions go through `submit_with_retry()`
which handles retryable engine results: `telINSUF_FEE_P`, `terRETRY`,
`terQUEUED`, `terPRE_SEQ`.

**Fix #7 — Trust boundary.** `active_coverage_drops` is now derived on-chain
by reading `AccountNFTs` and summing the `"c"` field from each Ward policy NFT.
It is no longer accepted as a caller parameter. Additionally:
- Owner reserve is calculated as `base_reserve + (OwnerCount × 2 XRP)` — not flat 20 XRP.
- URI hex is asserted ≤ 512 chars before every network call.

### 3-Tier Licensing Integration

The three licensing tiers from `index.html` are now enforced in code, not just documentation.
`LicenseTier` and `TIER_MINT_GATES` live in `ward/constants.py`.
`PoolHealthMonitor.is_minting_allowed(health, tier)` gates minting at the correct risk level.

| Tier | Pool Risk Gate |
|---|---|
| Starter | safest / safe / moderate only |
| Standard | + elevated |
| Enterprise | + elevated (high always blocks all tiers) |

### Test Suite Migration (fix #8)

`test_ward.py` was migrated from `ward_client` imports to `ward.*` imports.
The mock pattern changed from `validator._client = MagicMock()` (injecting a private
attribute) to patching `ward.validator.AsyncJsonRpcClient` with a proper async
context-manager mock.

`PoolHealthMonitor.get_health()` now takes no arguments — coverage is derived
on-chain. Tests inject coverage by providing Ward policy NFTs in the
`AccountNFTs` mock response.

### Backward Compatibility

`ward_client.py` (root) was converted to a thin deprecation shim. It:
- Issues a `DeprecationWarning` at import time
- Re-exports every previously public symbol from the new `ward.*` modules
- Is scheduled for removal in v0.3.0

---

## v0.1.x — Initial Modular Split  (March 2026)

### Motivation

The original application was a FastAPI server with all XRPL logic
embedded in route handlers and application code. The v0.1.x refactor
separated the protocol layer (Ward SDK) from the application layer.

### What Changed

A root-level `ward/` package was introduced with three modules:

```
ward/
├── __init__.py       Exports TxBuilder, ChainReader, WardMonitor
├── tx_builder.py     Build Payment, EscrowCreate, EscrowFinish, EscrowCancel
├── chain_reader.py   AccountInfo, AccountObjects, AccountTx, LedgerEntry queries
└── monitor.py        Polling-based vault balance monitoring
```

These are still present in v0.2.x as legacy infrastructure modules.
`monitor.py` is polling-only and NOT suitable for production default detection —
use `ward.VaultMonitor` (WebSocket + 3-ledger confirmation) instead.

### Integration Points

| Consumer | Module |
|---|---|
| API / application layer | `ward.chain_reader.ChainReader` for read queries |
| SDK modules | `ward.tx_builder.TxBuilder` for unsigned tx construction |
| Production monitoring | `ward.VaultMonitor` (not `ward.monitor.WardMonitor`) |

---

## Core Invariant (all versions)

Ward never holds wallet keys. This is not a policy — it is a structural guarantee.
No Ward class stores a wallet. No Ward method signs a transaction.
The institution's wallet exists only within the scope of a single method call,
passed as a parameter, never stored.

```python
# NEVER
self._wallet = wallet   # Ward never does this

# ALWAYS — wallet lives only in the call frame
async def purchase_coverage(self, wallet: Wallet, ...):
    tx = NFTokenMint(account=wallet.classic_address, ...)
    async with AsyncJsonRpcClient(self._url) as client:
        await submit_with_retry(client, tx, wallet)
    # wallet goes out of scope here
```
