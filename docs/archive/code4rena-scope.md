# Ward Protocol — Code4rena Audit Scope

**Contest:** Ward Protocol v0.2.2 — Institutional DeFi Insurance SDK  
**Chain:** XRP Ledger (XRPL) — XLS-66 lending vaults, XLS-20 NFTs, XLS-70 credentials  
**Language:** Python 3.11+ (primary); Rust (secondary)  
**Date prepared:** 2026-05-01  
**Version:** 0.2.2  

---

## Overview

Ward Protocol is an open-source insurance layer for XLS-66 institutional lending vaults on the XRP Ledger. It provides:

- **On-chain default detection** — trustless WebSocket monitor with 3-ledger confirmation
- **9-step claim validation** — all state sourced from XRPL ledger, no off-chain inputs trusted
- **PREIMAGE-SHA-256 escrow settlement** — claimant holds preimage; Ward only sees condition
- **Pool health monitoring** — coverage ratio enforcement and reserve accounting

**Core invariant:** `ward_signed = False` — Ward Protocol constructs unsigned transactions. Institutions sign; XRPL settles. Ward never holds, touches, or stores private keys.

---

## In-Scope Files

### Python SDK (Primary Target)

| File | nSLOC | Description |
|------|-------|-------------|
| `ward/constants.py` | ~95 | All protocol constants: taxons, flags, limits, endpoints |
| `ward/primitives.py` | ~220 | Validators, rate limiter, crypto helpers, submit_with_retry |
| `ward/validator.py` | ~220 | 9-step ClaimValidator — core claim validation logic |
| `ward/vault_monitor.py` | ~240 | VaultMonitor — WebSocket default detection, 3-ledger confirmation |
| `ward/settlement.py` | ~160 | EscrowSettlement — PREIMAGE-SHA-256 escrow lifecycle |
| `ward/pool.py` | ~175 | PoolHealthMonitor — coverage ratio, reserve accounting |
| `ward/client.py` | ~100 | WardClient — high-level SDK entrypoint |
| `ward/tx_builder.py` | ~100 | TxBuilder — unsigned transaction construction |
| `ward/chain_reader.py` | ~110 | ChainReader — XRPL ledger state queries |
| `ward/monitor.py` | ~90 | Monitor — async event dispatcher |
| `ward/__init__.py` | ~55 | Public API exports |

**Total Python nSLOC: ~1,565**

### Rust Modules (Secondary Target)

| File | nSLOC | Description |
|------|-------|-------------|
| `ward/src/monitor.rs` | ~340 | Rust VaultMonitor — WebSocket default detection |
| `ward/src/escrow.rs` | ~175 | Rust EscrowBuilder — condition/fulfillment derivation |
| `ward/src/error.rs` | ~18 | WardError enum |
| `ward/src/lib.rs` | ~12 | Crate exports |
| `ward/src/main.rs` | ~38 | CLI entrypoint |

**Total Rust nSLOC: ~583**

### **Total In-Scope nSLOC: ~2,148**

---

## Out-of-Scope Files

| File/Directory | Reason |
|----------------|--------|
| `ward_client.py` | Backward-compat shim; re-exports from `ward.*` only |
| `test_ward.py` | Test suite — not production code |
| `starter/` | Integration examples — not production code |
| `*.html` | Frontend pages — not audited |
| `scripts/` | Deployment scripts |
| `dashboard/` | Dashboard frontend |
| `demo/` | Demo scripts |
| `conftest.py` | pytest configuration |

---

## Attack Surface & Known Attack Vectors

The following 15 attack vectors have been mitigated in v0.2.2. Auditors should verify the mitigations are complete and cannot be bypassed.

### AV 2.1 — Policy Forgery
**Risk:** Attacker submits a claim with a forged or fake policy NFT.  
**Mitigation:** `ClaimValidator._step1_verify_nft_exists` checks `NFTokenTaxon == WARD_POLICY_TAXON (281)` and returns `_WRONG_TAXON` sentinel on mismatch.  
**Files:** `ward/validator.py:173–203`, `ward/constants.py`

### AV 2.2 — Double-Spend / Replay
**Risk:** Previously-settled claim replayed after NFT is burned.  
**Mitigation:** Step 1 verifies NFT exists in claimant's wallet right now. Ward burns the NFT during settlement; burned NFTs cannot pass step 1. Rate limiter (AV 2.12) provides additional replay resistance.  
**Files:** `ward/validator.py:173–203`

### AV 2.3 — Policy Transfer After Default Detection
**Risk:** Attacker sells/transfers policy NFT to a new owner after spotting a default signal, before the claim is processed.  
**Mitigation:** Policy NFTs use `TF_BURNABLE` (`0x1`) but deliberately omit `TF_TRANSFERABLE` (`0x8`). Non-transferable NFTs cannot be sold or transferred.  
**Files:** `ward/constants.py` (TF_BURNABLE/TF_TRANSFERABLE), `ward/client.py`

### AV 2.4 — WebSocket Signal Manipulation
**Risk:** Malicious WebSocket message injects false health ratios.  
**Mitigation:** `VaultMonitor` uses WebSocket events only as hints. `_verify_default_on_chain` re-fetches `LedgerEntry(index=loan_id)` via independent JSON-RPC before emitting `VerifiedDefault`.  
**Files:** `ward/vault_monitor.py:290–317`

### AV 2.5 — Clock Manipulation
**Risk:** Attacker manipulates system clock to bypass policy expiry check.  
**Mitigation:** `_step2_check_expiry` fetches `close_time` from `Ledger(ledger_index="validated")` via XRPL ledger — never uses `time.time()` or `datetime.now()`.  
**Files:** `ward/validator.py:232–242`, `ward/primitives.py:204–241`

### AV 2.6 — Escrow Front-Running
**Risk:** Attacker extracts preimage from the API request and uses it to front-run the EscrowFinish.  
**Mitigation:** `EscrowSettlement.create_claim_escrow` never accepts a preimage parameter. `EscrowRecord` has no preimage field. Ward only receives `condition_hex`; the preimage stays with the claimant.  
**Files:** `ward/settlement.py`

### AV 2.7 — VaultMonitor Endpoint Spoofing
**Risk:** Attacker configures VaultMonitor to connect to a malicious WebSocket server.  
**Mitigation:** `_validate_ws_url` in `vault_monitor.py` enforces: (1) `wss://` TLS required, (2) URL must be in `ALLOWED_WS_URLS` allowlist.  
**Files:** `ward/vault_monitor.py:352–371`, `ward/constants.py` (ALLOWED_WS_URLS)

### AV 2.8 — Pool Drainage
**Risk:** Multiple simultaneous claims drain the insurance pool below reserve.  
**Mitigation:** Step 9 checks `usable = balance − reserve ≥ payout` AND `ratio = usable / payout ≥ MIN_COVERAGE_RATIO (1.5)`. Step 6 performs an independent insolvent-pool check.  
**Files:** `ward/validator.py:296–314`, `ward/pool.py`

### AV 2.9 — Coverage Ratio Manipulation
**Risk:** Off-chain health ratio used to approve claims that would fail on-chain verification.  
**Mitigation:** Health ratio is re-fetched from the XRPL ledger at claim validation time (step 4). WebSocket-reported values are never trusted directly.  
**Files:** `ward/validator.py:244–272`

### AV 2.10 — Address Injection
**Risk:** SQL-injection-style or malformed addresses bypass validation.  
**Mitigation:** `validate_xrpl_address` uses xrpl-py's `is_valid_classic_address` (base58check) at every API boundary before any ledger queries.  
**Files:** `ward/primitives.py:68–80`, `ward/validator.py:83–94`

### AV 2.11 — Key Exfiltration via Instance State
**Risk:** Wallet or private key inadvertently stored as instance attribute.  
**Mitigation:** `WardClient` has no `_wallet` or `wallet` attribute. Wallet is passed as a parameter per-call and not retained. `validate_wallet()` enforces type at the boundary.  
**Files:** `ward/client.py`, `ward/primitives.py:182–196`

### AV 2.12 — Rate Limit Bypass
**Risk:** Attacker floods claim submissions to bypass per-NFT rate limiting.  
**Mitigation:** Thread-safe sliding-window rate limiter in `primitives.py`: max `CLAIM_RATE_LIMIT_MAX (3)` attempts per `CLAIM_RATE_LIMIT_WINDOW_S (300)` seconds per NFT token ID. Rate limit is checked at step 9 (after the cheap ledger reads, before the solvency check).  
**Files:** `ward/primitives.py:148–179`

### AV 2.13 — NFT Taxon Spoofing
**Risk:** Attacker mints an NFT with taxon 0 or another value and submits it as a Ward policy.  
**Mitigation:** `_step1_verify_nft_exists` checks `NFTokenTaxon == 281` (WARD_POLICY_TAXON). Returns `_WRONG_TAXON` sentinel (not `None`) so the claim is rejected at step 1 with a taxon-specific error.  
**Files:** `ward/validator.py:194–197`, `ward/constants.py`

### AV 2.14 — XRP / Drops Unit Confusion
**Risk:** Float amounts (e.g., `1.5` XRP) passed where integer drops are required.  
**Mitigation:** `validate_drops()` rejects floats, booleans, negatives, and values > `XRP_MAX_DROPS`. Called at every amount boundary.  
**Files:** `ward/primitives.py:100–122`

### AV 2.15 — Silent Network Failure / Heartbeat Timeout
**Risk:** WebSocket connection silently drops; VaultMonitor stops detecting defaults without error.  
**Mitigation:** `_run_with_heartbeat` wraps each `__anext__` call with `asyncio.wait_for(timeout=MONITOR_HEARTBEAT_TIMEOUT_S=60)`. Timeout raises `asyncio.TimeoutError` which triggers reconnect in the exponential-backoff loop.  
**Files:** `ward/vault_monitor.py:179–203`

---

## Key Protocol Invariants

Auditors should verify these invariants cannot be violated:

1. **`ward_signed = False`** — No method in any module signs a transaction. `submit_and_wait` is only called with a wallet passed by the institution at call time; no wallet is stored.

2. **Events are hints, ledger is truth** — `VaultMonitor` always performs an independent `LedgerEntry` RPC call to verify defaults. The WebSocket `transaction` message contents are never used to approve claims.

3. **3-ledger confirmation** — `DEFAULT_CONFIRM_COUNT` consecutive ledger closes must observe the default signal before `VerifiedDefault` is emitted.

4. **TF_BURNABLE only** — Policy NFTs have flags `TF_BURNABLE (0x1)` and explicitly NOT `TF_TRANSFERABLE (0x8)`. Verify this in `ward/client.py` NFTokenMint construction.

5. **WARD_POLICY_TAXON = 281** — Any NFT with taxon ≠ 281 must be rejected at step 1. Taxon 282 is `WARD_CREDENTIAL_TAXON` (KYC/AML) and must not be accepted as a policy.

6. **No off-chain trust** — The codebase must not trust any off-chain oracle, database, signed attestation, or caller-supplied state that isn't verified against the XRPL ledger.

---

## Severity Classification

We follow the standard Code4rena severity levels:

| Severity | Definition for Ward Protocol |
|----------|------------------------------|
| **Critical** | Enables unauthorized claim payout, theft of pool funds, or ward_signed=False invariant breach |
| **High** | Bypass of any single claim validation step, rate limit bypass, replay attack |
| **Medium** | Incorrect reserve calculation, taxon/flag enforcement gap, incorrect payout calculation |
| **Low** | Missing input validation at non-boundary locations, gas inefficiency, informational gaps |
| **Informational / QA** | Code quality, documentation, naming conventions |

---

## Testing

The repository includes a comprehensive test suite:

```
test_ward.py        — 146 tests (all passing)
                      Covers all 9 claim validation steps, all 15 attack vectors,
                      VaultMonitor, EscrowSettlement, PoolHealthMonitor, primitives
```

Run:
```bash
pip install -r requirements.txt
python -m pytest test_ward.py -m "not integration" -v
```

Coverage: 62% overall (higher on core modules: `constants.py` 100%, `primitives.py` 86%, `validator.py` 79%)

Rust tests:
```bash
cd ward && cargo test
```

---

## Deployment Context

- **Network:** XRPL Mainnet (primary) / Testnet (development)
- **Standards:** XLS-66 (lending vaults), XLS-20 (NFTs), XLS-70 (credentials), XLS-80 (permissioned domains)
- **Reserve model:** `base_reserve = 2 XRP`, `owner_reserve = 0.2 XRP` (mainnet values hardcoded in `constants.py`)
- **Escrow model:** PREIMAGE-SHA-256 crypto-conditions (RFC 3230 / IETF Crypto-Conditions)
- **License:** MIT

---

## Sponsor Information

**Protocol:** Ward Protocol  
**Contact:** wflores@wardprotocol.org  
**Docs:** [ward-protocol.xyz](https://ward-protocol.xyz)  
**Spec:** `docs/institutional-defi-insurance-specification.md`
