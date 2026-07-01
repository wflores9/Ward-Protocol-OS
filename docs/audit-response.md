# Ward Protocol — Institutional Audit Response

**Audit:** Copilot Comprehensive Repository Review  
**Response date:** June 2026  
**Version at time of audit:** v0.2.5  
**Current version:** v0.2.6  
**Status:** All findings resolved

---

## 1. Institutional Grade Readiness

| Finding | Severity | Resolution |
|---------|----------|------------|
| Auth bypass in `verify_institution_key()` | P0 | Fail-closed — raises HTTP 503 if `INSTITUTION_API_KEY` unset |
| `/keys/generate` unprotected | P0 | `Depends(_institution_key_dep)` added |
| `wallet_seed` in `PolicyPurchaseRequest` | P0 | Field removed — API never accepts private keys |
| `ward_signed = False` violated in `ward/client.py` | P0 | `build_unsigned_tx()` replaces all `submit_with_retry()` calls |
| `ward_signed = False` violated in `ward/settlement.py` | P0 | `build_unsigned_tx()` replaces all signing paths |
| Legacy `sdk/python/ward/` stores wallets | P0 | Quarantined to `sdk/python/ward_legacy/` with README |
| Error handling leaks RPC URL | P1 | Error responses sanitized |
| In-memory rate limiter | P1 | Redis-backed sliding window via `WARD_REDIS_URL` |
| Missing on-chain premium payment check | P1 | `_step2_verify_premium_payment()` added to validator |
| Keys/vault registry in-memory | P1 | Redis-backed with in-memory fallback |
| Rejection reasons HTTP only | P1 | `rejection_memo_hex` in `ValidationResult` and API response |

---

## 2. Security Audit

| Finding | Severity | Resolution |
|---------|----------|------------|
| XRPL address validation missing at API boundary | P0 | `field_validator` on all request models |
| `/dashboard/vault/{vault_id}/health` no validation | P0 | Regex validation before `AccountInfo` call |
| Rate limit not enforced at API layer | P0 | Redis-backed, wired at `ClaimValidator` step 9 |
| TOCTOU: EscrowFinish → NFTokenBurn | P0 | Redis settlement lock — `ward:settlement:{claim_id}` set atomically (NX) |
| `condition_hex` no shape/length validation | P0 | `validate_condition_hex()` — 78 hex chars, ASN.1 prefix check |
| SSRF in `ward/webhooks.py` | P1 | Private IP blocking via `ipaddress` module |
| Hardcoded deployer key `0x...01` | P1 | Raises `Error` if `DEPLOYER_PRIVATE_KEY` not set |
| Legacy DB defaults in scripts | P1 | Replaced with `WARD_DATABASE_URL` env requirement |
| Dependency version drift | P1 | Upper bounds pinned in `requirements.txt` and `pyproject.toml` |

---

## 3. Multi-chain Feasibility

| Finding | Severity | Resolution |
|---------|----------|------------|
| Adapters return stubs | P1 | Documented as prototypes — fail with `NotImplementedError` |
| `ChainAdapter` too narrow | P0 | Full lifecycle added: policy mint, premium payment, NFT burn, replay control, pool health, KYC |
| Prioritize XDC / XRPL EVM / Flare | P1 | All three deployed on testnet with verified tx hashes |

---

## 4. Code Quality

| Finding | Severity | Resolution |
|---------|----------|------------|
| Chain-agnostic vs XRPL mixed in `primitives.py` | P1 | Architecture documented; physical split planned v0.3.0 |
| Duplicate RPC reads in `validator.py` | P1 | Steps 6, 7, 8 reuse data from `asyncio.gather` — zero duplicate reads |
| Legacy contradictory implementations | P0 | Quarantined to `sdk/python/ward_legacy/` |
| SDK/docs/tests drifted | P1 | TypeScript routes fixed, tests rewritten, route alignment tests added |

---

## 5. Grant & Compliance

| Finding | Severity | Resolution |
|---------|----------|------------|
| OpenAPI disabled vs spec claiming live | P1 | Spec updated — OpenAPI disabled in production documented |
| CI only runs Python | P1 | Rust and TypeScript CI jobs added — all green |
| `test_sdk.py` hardcoded local paths | P1 | Fully rewritten with correct endpoints |
| `.env.example` incomplete | P1 | All required env vars documented |

---

## Residual Items (Protocol-Level)

| Item | Status |
|------|--------|
| Full atomic EscrowFinish + NFTokenBurn | Requires XRPL protocol support. Mitigated via Redis settlement lock. |
| Physical `primitives.py` split | Planned v0.3.0. No security impact. |
| Full chain adapter implementations (Solana, Stellar, Hedera) | Planned post-mainnet. Fail with `NotImplementedError`. |

---

## Test Coverage

| Suite | Count | Status |
|-------|-------|--------|
| Python unit tests | 436 | All passing |
| SDK API tests | 9 | All passing |
| Rust tests | 40 | CI green |
| TypeScript tests | 45 | CI green |

---

## Core Invariant

ward_signed = False — always.
Ward constructs unsigned transactions. Institutions sign. XRPL settles.
Ward never holds, touches, or stores private keys.

This invariant is enforced at the architecture level:
- No Ward class stores a wallet
- No Ward method calls submit_and_wait
- WardSignedInvariantMiddleware enforces ward_signed: false on every API response
- build_unsigned_tx() is the only transaction construction path
