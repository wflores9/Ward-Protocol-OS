# Ward Protocol — Multi-Chain Integration Index

> **Core invariant: `ward_signed = False` — always.**  
> Ward constructs unsigned transactions. Institutions sign. The chain settles.  
> This invariant is preserved identically on every target chain below.  
> Ward never holds a private key. Ward never signs a transaction. On any chain.

---

## Integration Phases

| Phase | Chain | Priority | Key Tech | Grant Program | Amount | Status |
|---|---|---|---|---|---|---|
| 2 (1.5) | **Flare EVM** | 🔴 Highest | Solidity + FDC cross-chain | Flare Grants + Google Cloud | Up to $200K | Planning |
| 2 | **Hedera** | 🟠 High | Solidity + HCS + HTS | Hedera Foundation | TBD | Planning |
| 3 | **Solana** | 🟠 High | Rust/Anchor + Metaplex pNFT | Solana Foundation | TBD | Planning |
| 4 | **Stellar** | 🟡 Medium | Rust/Soroban + Horizon SSE | Stellar Community Fund | Up to $150K | Planning |

---

## Phase Documents

- [Phase 2 (1.5) — Flare EVM](./phase2-flare.md)
- [Phase 2 — Hedera](./phase2-hedera.md)
- [Phase 3 — Solana](./phase3-solana.md)
- [Phase 4 — Stellar/Soroban](./phase4-stellar.md)

---

## Core File Porting Summary

| File | What It Does | XRPL-Specific | Chain-Agnostic | Complexity |
|---|---|---|---|---|
| `ward/validator.py` | 9-step claim validation, all state from ledger | `AccountNFTs`, `LedgerEntry`, `AccountInfo`, XLS-20 taxon, XLS-66 flags, XRPL reserve model | Step sequence logic, `ValidationResult`, rate limit check, coverage ratio, metadata parsing | **High** |
| `ward/vault_monitor.py` | WebSocket default detection, 3-ledger confirmation | `AsyncWebsocketClient`, `Subscribe`, `LedgerEntry`, `LSF_LOAN_DEFAULT`, `ALLOWED_WS_URLS`, XLS-66 fields | 3-confirmation logic, exponential backoff, heartbeat timeout, `DefaultSignal`/`VerifiedDefault` dataclasses | **High** |
| `ward/client.py` | Policy purchase: premium payment + NFT mint | `NFTokenMint`, `Payment`, `TF_BURNABLE`, taxon 281, `str_to_hex`, `Memo`, `autofill`, `submit_and_wait` | Premium calculation, license tier gating, compact JSON metadata, `register_pool_member` pattern | **High** |
| `ward/settlement.py` | PREIMAGE-SHA-256 escrow lifecycle | `EscrowCreate`, `EscrowFinish`, `EscrowCancel`, `NFTokenBurn`, Ripple epoch time, `offer_sequence` | `EscrowRecord` dataclass, dispute/cancel window enforcement, preimage lifecycle, error patterns | **High** |
| `ward/tx_builder.py` | Unsigned transaction construction | All XRPL models (`EscrowCreate`, `Payment`, etc.), `datetime_to_ripple_time`, `str_to_hex` Memo format | `TxBuilder` static method pattern, `EscrowParams` concept, dispute window timing | **High** |
| `ward/primitives.py` | Error types, validators, crypto, rate limiter | `is_valid_classic_address`, `Ledger`/`ServerInfo` RPC, `RIPPLE_EPOCH_OFFSET`, `submit_and_wait`, retryable engine results | `WardError` hierarchy, `make_preimage_condition()`, `generate_claim_preimage()`, `check_rate_limit()`, `validate_drops()`, `validate_loan_id()` | **Medium** |
| `ward/constants.py` | Protocol constants: flags, taxons, rates, tiers | `WARD_POLICY_TAXON`, `TF_BURNABLE`, `LSF_LOAN_DEFAULT`, XRPL reserve amounts, WS allowlist, `RIPPLE_EPOCH_OFFSET` | `MIN_COVERAGE_RATIO`, rate limit params, escrow timing, `LicenseTier`, risk tier thresholds, `MONITOR_HEARTBEAT_TIMEOUT_S` | **Low** |

---

## Most XRPL-Specific (Hardest to Port)

**These files require the most chain-specific work:**

1. **`ward/tx_builder.py`** — Every method builds an XRPL-specific transaction model. No shared logic survives verbatim; the pattern (static builders returning unsigned tx objects) survives.
2. **`ward/settlement.py`** — XRPL's native escrow model (`EscrowCreate`/`EscrowFinish` with `offer_sequence`) has no equivalent on EVM chains. Requires a dedicated Solidity/Anchor/Soroban contract per chain.
3. **`ward/client.py`** — Every operation (`NFTokenMint`, `Payment`, `AccountSet`) is an XRPL transaction type. XLS-20 NFT mechanics (taxon, flags) are XRPL-only.
4. **`ward/vault_monitor.py`** — The WebSocket subscription model (`Subscribe` to XRPL ledger stream) and XLS-66 field names (`LSF_LOAN_DEFAULT`, `AffectedNodes`, `PrincipalOutstanding`) are entirely XRPL-specific.
5. **`ward/validator.py`** — All 9 steps query XRPL-specific ledger objects. Steps 4 and 5 in particular depend on XLS-66 `LedgerEntry` flags that have no direct parallel on other chains.

---

## Most Chain-Agnostic (Easiest to Reuse)

**These functions or modules port with minimal changes:**

1. **`make_preimage_condition()`** (`primitives.py`) — Pure SHA-256 math from RFC 3230. The `A0 25 80 20 <hash> 81 01 20` ASN.1 encoding is chain-agnostic. The same function works on every target chain.
2. **`generate_claim_preimage()`** (`primitives.py`) — `secrets.token_bytes(32)` has identical equivalents on every platform.
3. **`check_rate_limit()`** (`primitives.py`) — Sliding-window rate limiter with threading lock. On-chain implementations (Solidity mapping, Soroban persistent storage) use the same logic.
4. **`validate_drops()`** / **`validate_loan_id()`** / **`validate_nft_id()`** (`primitives.py`) — Input validation patterns (integer-only amounts, 64-char hex IDs) port verbatim with language-appropriate syntax.
5. **`LicenseTier`** + business constants (`constants.py`) — `MIN_COVERAGE_RATIO`, `CLAIM_RATE_LIMIT_MAX`, `ESCROW_DISPUTE_HOURS`, tier thresholds, premium rates — all chain-agnostic.
6. **`ValidationResult`** dataclass (`validator.py`) — The return contract (approved, payout, reason, steps_passed) is chain-agnostic and should be preserved across all implementations.
7. **`EscrowRecord`** dataclass (`settlement.py`) — The fields (claim_id, pool, claimant, payout, condition, timing) map directly to on-chain storage structs on Solidity/Anchor/Soroban.
8. **3-ledger confirmation pattern** (`vault_monitor.py`) — The `DefaultSignal` → `VerifiedDefault` confirmation count logic maps to 3-block confirmation on any chain.

---

## Recommended Porting Order (by complexity)

```
1. ward/constants.py     → Split: chain-specific section + chain-agnostic section
                           (Low complexity — defines the target for all other ports)

2. ward/primitives.py    → Port chain-agnostic functions verbatim; replace XRPL-specific
                           address validation + ledger time per target chain
                           (Medium complexity — clean split already visible in source)

3. ward/validator.py     → Port step logic; replace each XRPL RPC call with
                           chain-appropriate equivalent per step
                           (High complexity — but step sequence is the guide)

4. ward/vault_monitor.py → Port confirmation + heartbeat + backoff logic;
                           replace XRPL WebSocket with chain-native event stream
                           (High complexity — but pure async I/O, no business logic)

5. ward/settlement.py    → Port EscrowRecord + timing logic; implement escrow
                           as native contract (Solidity/Anchor/Soroban)
                           (High complexity — XRPL escrow model is unique)

6. ward/tx_builder.py    → Port static builder pattern; every method is
                           chain-specific, nothing reuses verbatim
                           (High complexity — pure XRPL transaction assembly)

7. ward/client.py        → Port last; depends on all the above being settled
                           (High complexity — orchestrates all modules)
```

---

## The Invariant That Never Changes

Across every chain, in every language, in every contract:

```python
# XRPL (Python)
ward_signed = False

# EVM (Solidity)
bool constant WARD_SIGNED = false;

# Solana (Rust/Anchor)
const WARD_SIGNED: bool = false;

# Stellar (Rust/Soroban)
const WARD_SIGNED: bool = false;
```

Ward constructs. Institutions sign. The chain settles.
