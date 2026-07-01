# Ward Protocol — Multi-Chain Abstraction Gaps

**Date:** 2026-06-10  
**Scope:** `ward/chain.py` (ABC), `ward/adapters/` (7 non-XRPL adapters)  
**Purpose:** Audit-only inventory of gaps between the adapter contract and actual implementations. No refactoring performed.

---

## Architecture Overview

```
ward/chain.py
└── ChainAdapter (ABC)
    ├── verify_vault()           → bool
    ├── get_ledger_state()       → LedgerState
    ├── build_resolution_tx()    → UnsignedTransaction
    ├── get_policy_certificate() → dict
    ├── get_ledger_time()        → int
    └── ... (chain-specific extensions)

ward/adapters/
├── flare.py      (FlareAdapter)
├── hedera.py     (HederaAdapter)
├── solana.py     (SolanaAdapter)
├── stellar.py    (StellarAdapter)
├── xdc.py        (XDCAdapter)
├── axelar.py     (AxelarAdapter)    ← cross-chain bridge
└── wormhole.py   (WormholeNTTAdapter) ← cross-chain bridge
```

---

## Implementation Status

### Method Completeness

Each adapter has 6 methods with `raise NotImplementedError` (42 total stubs):

| Adapter | verify_vault | get_ledger_state | build_resolution_tx | get_policy_cert | get_ledger_time | 6th method |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| flare.py | stub | stub | stub | stub | stub | stub |
| hedera.py | stub | stub | stub | stub | stub | stub |
| solana.py | stub | stub | stub | stub | stub | stub |
| stellar.py | stub | stub | stub | stub | stub | stub |
| xdc.py | stub | stub | stub | stub | stub | stub |
| axelar.py | stub | stub | stub | stub | stub | stub |
| wormhole.py | stub | stub | stub | stub | stub | stub |

All adapters have: constructor with `require_non_placeholder()` validation, data classes (`VaultState`, `LedgerState`, `*Payload`), and detailed docstrings describing the intended behavior. The scaffolding is complete; only the HTTP/RPC calls are stubbed.

### Placeholder Addresses (blocked by `require_non_placeholder()`)

| Adapter | Placeholder | Field |
|---------|-------------|-------|
| flare.py | `"0x0000000000000000000000000000000000000000"` | `_rlusd_address` |
| hedera.py | `"0.0.0"` | `_rlusd_token_id` |
| solana.py | `"11111111111111111111111111111111"` | `_rlusd_mint` |
| stellar.py | `"GXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"` | `_rlusd_issuer` |
| xdc.py | `"0x0000000000000000000000000000000000000000"` | `_rlusd_address` |
| axelar.py | `"0x0000000000000000000000000000000000000000"` | `_gateway_address` |
| wormhole.py | (XRPL currency hex) | `_rlusd_currency` |

`require_non_placeholder()` raises at instantiation if a placeholder value is passed. This is the correct safety pattern — a misconfigured adapter will fail fast rather than silently misroute funds.

---

## XRPL Logic Leaking Outside Adapter Layer

The main XRPL-specific logic lives in `ward/validator.py`, `ward/primitives.py`, `ward/tx_builder.py`, `ward/settlement.py`, and `ward/pool.py`. This is expected for the current XRPL-only production code. The concern is whether that logic is encapsulated or will need to be surgically extracted for a second chain.

### Encapsulation Assessment

| Concern | Location | Assessment |
|---------|----------|------------|
| `validate_xrpl_address()` | primitives.py, exported in `__init__.py` | Must become `validate_address(chain, addr)` for second chain |
| `XRPL_BASE_RESERVE_DROPS` | constants.py, used in pool.py and settlement.py | Must become chain-specific reserve lookup |
| NFT taxon 281 check | validator.py step 1 | XRPL-specific (XLS-20); other chains use different NFT standards |
| `LedgerEntry(index=loan_id)` / `LSF_LOAN_DEFAULT` | validator.py step 4 | Pure XLS-66 — must be reimplemented per chain |
| Drops arithmetic (1 XRP = 1,000,000 drops) | primitives.py, settlement.py | XRPL-specific unit; other chains have different precision |
| `AccountNFTs` / `NFTokenBurn` / `EscrowCreate` | tx_builder.py, settlement.py | All XRPL transaction types — chain-specific |
| PREIMAGE-SHA-256 escrow | settlement.py, validator.py | XRPL crypto-condition standard; Stellar has similar but different wire format |
| `get_active_coverage_drops()` memo parsing | coverage.py | XRPL transaction memo format |

**Wormhole adapter is the highest XRPL leakage point.** The `WormholeNTTAdapter` has `_WORMHOLE_CHAIN_ID_XRPL = 25` and `_RLUSD_XRPL_CURRENCY` hardcoded, and comments reference XLS-66 and XRPL reserve drops directly. This is partially intentional (Wormhole bridges from XRPL to other chains) but the comments on `get_pool_balance()` ("Steps 6 + 9: Get usable pool balance minus XRPL reserve") will be wrong when the source chain is not XRPL.

---

## Ordered Refactor List for Second Mainnet Chain

Listed by effort, ascending (easiest first):

### Level 1 — Mechanical, Low Risk (~1 day each)

1. **Address validation abstraction** (`ward/primitives.py`)  
   - Extract `validate_xrpl_address()` → `validate_address(chain: str, addr: str)`  
   - Add chain-specific validators in adapter constructors  
   - Impact: 8 call-sites in client.py, registry.py, webhooks.py, monitor.rs

2. **Implement one adapter's stub methods** (pick Stellar — most similar to XRPL; same PREIMAGE-SHA-256, similar account model)  
   - `stellar.py`: implement 6 methods using `stellar-sdk` (already a dependency via pyproject.toml?)  
   - This proves the adapter pattern works end-to-end before the others

3. **Config validation at startup** (`ward/adapters/_config.py`)  
   - `require_non_placeholder()` already exists — add a `validate_all_adapters()` registry function  
   - Call from server startup, not just at instantiation  

### Level 2 — Moderate Effort (~3 days each)

4. **Chain-specific reserve abstraction** (`ward/constants.py`, `ward/pool.py`)  
   - Replace `XRPL_BASE_RESERVE_DROPS` constant with `get_reserve(chain, ledger_state)` function  
   - XRPL adapter returns 20_000_000 drops; Stellar adapter returns 1 XLM (10_000_000 stroops); etc.  

5. **Drops/amount unit abstraction** (`ward/primitives.py`, `ward/settlement.py`)  
   - Replace bare drops arithmetic with `Amount(value: int, unit: str, chain: str)` dataclass  
   - Affects 20+ sites in settlement.py and pool.py  

6. **NFT standard abstraction** (`ward/validator.py` steps 1, 7, 8)  
   - Steps 1/7/8 assume XLS-20 NFTs (taxon 281, `AccountNFTs`, `NFTokenBurn`)  
   - Needs per-chain `get_policy_nft(chain, token_id)`, `burn_policy_nft(chain, token_id)`  

### Level 3 — Architecture Work (~1 week)

7. **LedgerEntry/LSF_LOAN_DEFAULT abstraction** (`ward/validator.py` step 4)  
   - The XLS-66 default flag is XRPL-specific; Stellar uses trustline flags, Flare uses contract state  
   - Requires abstracting the "is this loan in default?" query into `ChainAdapter.is_loan_default(loan_id)`  

8. **Crypto-condition portability** (`ward/settlement.py`, `ward/validator.py`)  
   - PREIMAGE-SHA-256 escrow is first-class on XRPL and Stellar; other chains need smart contract escrow  
   - The `condition_hex` / `fulfillment_hex` fields in claim flow are XRPL wire format  
   - Requires `build_escrow_release_tx(chain, ...)` abstraction in ChainAdapter  

9. **Rate limiter per-chain scope** (`ward/primitives.py`)  
   - Current: `check_rate_limit(nft_token_id)` — single namespace  
   - Multi-chain: same NFT-equivalent ID may exist on multiple chains  
   - Requires `check_rate_limit(chain, token_id)` after B2 Redis migration  

---

## Multi-Chain Demo vs Production

The live multi-chain testnet demo in `dashboard/` and `sdk/typescript/` connects to 8 testnet rails using the ChainAdapter pattern. The demo uses placeholder/mock responses from the adapters' unimplemented stubs. This is correct for demo purposes but **the demo cannot be used to validate that the adapters are production-ready** — the stubs return hardcoded mock data.

---

## Recommendation

**For Ward Protocol v1 mainnet:** Focus exclusively on the XRPL implementation. Ensure all 4 mainnet blockers (see MAINNET_READINESS.md) are closed before go-live. The multi-chain adapters should remain in `ward/adapters/` as scaffolding with `raise NotImplementedError` stubs and no production traffic.

**For Ward Protocol v2 (second chain):** Begin with Stellar. The Stellar PREIMAGE-SHA-256 escrow, XLM-native reserve model, and asset trustline model are closest to XRPL. The refactor sequence above levels 1→2→3 gives the right dependency order. Estimate 3-4 weeks of engineering to bring Stellar from stub to testnet-ready.
