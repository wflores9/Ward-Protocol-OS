# Phase 4 — Ward Protocol on Stellar / Soroban

**Chain:** Stellar (Soroban smart contracts, Rust)  
**Priority:** Medium  
**Grant:** Stellar Community Fund (SCF) — communityfund.stellar.org  
**Grant Amount:** Up to $150K, rounds every 4 weeks  
**Status:** Planning

---

## Overview

Stellar's Soroban smart contract platform (launched 2024) provides a Rust-based WASM execution environment that closely mirrors Solana's Sealevel model. Ward Protocol maps naturally:

| Ward (XRPL) | Stellar/Soroban |
|---|---|
| XLS-20 NFT (policy) | Soroban non-transferable token contract |
| XLS-66 vault | Soroban lending vault contract |
| XRPL escrow | Soroban PREIMAGE-SHA-256 contract |
| VaultMonitor WebSocket | Horizon API SSE stream |
| `ClaimValidator` (Python) | Soroban `WardClaimValidator` contract (Rust) |
| XRP drops | USDC on Stellar (7 decimal places, i128) |
| `validate_xrpl_address()` | Soroban `Address` type (built-in validation) |

---

## Stellar Anchor Network Context

Stellar's anchor network is the primary institutional on/off-ramp layer for USDC on Stellar. Ward Protocol's default resolution is directly relevant to:

- **Stellar anchors** that issue tokenized credit obligations
- **USDC lending pools** deployed via Soroban
- **Cross-border trade finance** where Stellar SEP-0031 handles the payment rail and Ward handles default resolution

Ward's `ward_signed = false` invariant maps perfectly to Stellar's design philosophy: Stellar separates the transaction construction from the signing authority. Institutions hold Stellar keypairs; Ward constructs unsigned Soroban invocations.

---

## SEP-0010 Identity Integration

Stellar's SEP-0010 provides challenge/response wallet authentication. Ward can leverage this for claimant identity verification at the API boundary without storing any credentials:

```
Claimant                    Ward API              Stellar
    |                          |                      |
    |── GET /auth/challenge ──>|                      |
    |<─ SEP-0010 challenge ────|                      |
    |                          |                      |
    |── POST /auth/token ─────>|                      |
    |   (signed challenge)     |                      |
    |                          |── verify signature ─>|
    |                          |<─ verified ──────────|
    |<─ JWT token ─────────────|                      |
    |                          |                      |
    |── validateClaim() ──────>|                      |
    |   (JWT + claim params)   |── Soroban invoke ───>|
```

Ward never stores the claimant's keypair — SEP-0010 proves ownership at the API boundary only.

---

## Architecture

```
Institution (Stellar keypair)
        |
        v
  ward-client (Rust/TypeScript)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  WardPolicyToken (Soroban non-transferable)         │
  │    - mint() on coverage purchase                    │
  │    - burn() on settlement                           │
  │    - Metadata stored in contract storage            │
  │                                                     │
  │  VaultMonitor (Horizon API SSE)                     │
  │    - Stream: /accounts/{vault_id}/transactions      │
  │    - Filter for vault default operations            │
  │    - 3-ledger confirmation                          │
  │    - Heartbeat: 60s timeout → reconnect             │
  │                                                     │
  │  WardClaimValidator (Soroban contract)              │
  │    - 9-step validation against Soroban state        │
  │    - All state from Stellar ledger                  │
  │    - Returns: approved, payout, reason_code         │
  │                                                     │
  │  WardEscrow (Soroban, PREIMAGE-SHA-256)             │
  │    - USDC escrow: pool → claimant                   │
  │    - condition: sha256(preimage) stored on-chain    │
  │    - Claimant calls finish with preimage            │
  │    - ward_signed = false — contract holds no keys  │
  │                                                     │
  └─────────────────────────────────────────────────────┘
        |
        v
  Stellar Consensus Protocol (SCP)
```

---

## Step-by-Step Porting Guide

### Step 1 — Constants (`ward/constants.py` → `ward_constants/src/lib.rs`)

```rust
// Soroban i128 amounts (USDC: 7 decimal places, 1 USDC = 10_000_000 stroops)
pub const MIN_COVERAGE_RATIO_X100: i128 = 150; // 1.5 × 100
pub const CLAIM_RATE_LIMIT_MAX: u32 = 3;
pub const CLAIM_RATE_LIMIT_WINDOW: i64 = 300; // seconds
pub const ESCROW_DISPUTE_SECS: i64 = 48 * 3600;
pub const ESCROW_CANCEL_SECS: i64 = 72 * 3600;
pub const DEFAULT_CONFIRM_COUNT: u32 = 3;

// Stellar has no base reserve model like XRPL's 20 XRP — no equivalent needed
// Soroban contracts use storage fees, not account reserves
```

### Step 2 — Primitives (`ward/primitives.py` → Soroban Rust)

```rust
// Soroban environment provides sha256 via env.crypto().sha256()
use soroban_sdk::{crypto::Hash, Env};

pub fn verify_preimage(env: &Env, preimage: &Bytes, condition: &BytesN<32>) -> bool {
    let hash: BytesN<32> = env.crypto().sha256(preimage);
    hash == *condition
}

// Rate limit: Soroban persistent storage per nft_id
// env.storage().persistent().set(&rate_key, &timestamps_vec)
// Soroban Address type validates automatically — no validate_xrpl_address() needed
```

Chain-agnostic ports:
- `make_preimage_condition()` → `env.crypto().sha256(preimage)` + fulfillment encoding
- `check_rate_limit()` → Soroban persistent storage `Map<Address, Vec<u64>>`
- Error hierarchy → Soroban `contracterror` enum

### Step 3 — ClaimValidator (`ward/validator.py` → Soroban contract)

```rust
#[contract]
pub struct WardClaimValidator;

#[contractimpl]
impl WardClaimValidator {
    pub fn validate_claim(
        env: Env,
        claimant: Address,
        nft_id: BytesN<32>,
        defaulted_vault: Address,
        loan_id: BytesN<32>,
        pool_address: Address,
    ) -> ValidationResult {
        // Step 1: policy token exists + non-transferable type
        // Step 2: block.timestamp (env.ledger().timestamp()) < expiry
        // Step 3: token metadata vault == defaulted_vault
        // Step 4: vault_contract.is_defaulted(loan_id)
        // Step 5: vault_contract.outstanding_amount(loan_id) > 0
        // Step 6+9: pool_contract.usdc_balance() >= vault_loss × 1.5
        // Step 7: token not burned (still exists in registry)
        // Step 8: token.owner() == claimant
        // Step 9: rate limit check via persistent storage
    }
}
```

Soroban contract calls (cross-contract invocation, CCI) replace XRPL `client.request()` calls. Vault and pool contracts are invoked via `env.invoke_contract()`.

### Step 4 — Policy Token (`NFTokenMint` → Soroban non-transferable token)

```rust
#[contract]
pub struct WardPolicyToken;

#[contractimpl]
impl WardPolicyToken {
    pub fn mint(env: Env, to: Address, metadata: PolicyMetadata) -> u64 {
        // ward_signed = false: institution calls mint, contract stores metadata
        let token_id = Self::next_token_id(&env);
        env.storage().persistent().set(&token_key(token_id), &metadata);
        env.storage().persistent().set(&owner_key(token_id), &to);
        token_id
    }

    pub fn transfer(_env: Env, _from: Address, _to: Address, _id: u64) {
        // Non-transferable: always panic (attack vector 2.3)
        panic!("WardPolicy: non-transferable");
    }

    pub fn burn(env: Env, owner: Address, token_id: u64) {
        owner.require_auth();
        let stored_owner: Address = env.storage().persistent().get(&owner_key(token_id))
            .expect("Token not found");
        assert_eq!(owner, stored_owner, "Not token owner");
        env.storage().persistent().remove(&token_key(token_id));
        env.storage().persistent().remove(&owner_key(token_id));
    }
}
```

### Step 5 — EscrowSettlement (`ward/settlement.py` → Soroban WardEscrow)

```rust
#[contracttype]
pub struct EscrowRecord {
    pub pool: Address,
    pub claimant: Address,
    pub amount: i128,            // USDC stroops
    pub condition: BytesN<32>,   // sha256(preimage)
    pub finish_after: u64,       // env.ledger().timestamp() + 48h
    pub cancel_after: u64,       // env.ledger().timestamp() + 72h
    pub settled: bool,
    pub nft_id: u64,
}

#[contractimpl]
impl WardEscrow {
    pub fn finish_escrow(env: Env, claim_id: BytesN<32>, preimage: Bytes) {
        let record: EscrowRecord = env.storage().persistent()
            .get(&claim_id).expect("Escrow not found");

        let now = env.ledger().timestamp();
        assert!(now >= record.finish_after, "Dispute window open");
        assert!(now < record.cancel_after, "Escrow expired");

        // Verify preimage
        let hash: BytesN<32> = env.crypto().sha256(&preimage);
        assert_eq!(hash, record.condition, "Bad preimage");

        // Transfer USDC (Stellar Asset Contract for USDC)
        let usdc = StellarAsset::new(env.clone(), USDC_ADDRESS);
        usdc.transfer(&env.current_contract_address(), &record.claimant, &record.amount);

        // Burn policy NFT
        let policy = WardPolicyToken::new(env.clone(), POLICY_TOKEN_ADDRESS);
        policy.burn(record.claimant.clone(), record.nft_id);

        // Mark settled
        let mut r = record;
        r.settled = true;
        env.storage().persistent().set(&claim_id, &r);
    }
}
```

### Step 6 — VaultMonitor (Horizon API SSE → Python/TypeScript)

```python
import asyncio, aiohttp, json

HORIZON_URL = "https://horizon.stellar.org"

async def monitor_vault(vault_id: str, on_verified_default):
    confirm_counts = {}
    url = f"{HORIZON_URL}/accounts/{vault_id}/transactions?cursor=now"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Accept": "text/event-stream"}) as resp:
            async for line in resp.content:
                data = parse_sse_event(line)
                if not data:
                    continue
                tx = json.loads(data)
                if is_default_operation(tx):
                    loan_id = extract_loan_id(tx)
                    confirm_counts[loan_id] = confirm_counts.get(loan_id, 0) + 1
                    if confirm_counts[loan_id] >= DEFAULT_CONFIRM_COUNT:
                        await on_verified_default(vault_id, loan_id, tx)
                        confirm_counts[loan_id] = 0
```

Heartbeat: Horizon SSE streams send `\n` keepalives. Implement 60s timeout via `asyncio.wait_for()` — same pattern as XRPL `VaultMonitor._run_with_heartbeat()`.

---

## SCF Grant Application Guide

**Stellar Community Fund:** communityfund.stellar.org  
**Round cadence:** Every 4 weeks  
**Amount:** Up to $150K  
**Format:** Application + community vote

**Application structure for Ward Protocol:**

```
Title: Ward Protocol — Deterministic Default Resolution for Soroban Lending

Problem: No standard exists for what happens when a borrower defaults on a
Stellar lending vault. Each protocol defines its own resolution logic —
or has none. This creates counterparty risk, audit gaps, and regulatory exposure.

Solution: Ward Protocol defines a 9-step on-chain validation sequence that
runs deterministically against Soroban ledger state. No oracle, no human
judgment, no Ward signature. The audit trail is the Stellar ledger.

Deliverables:
  1. WardClaimValidator Soroban contract (9-step validation)
  2. WardEscrow Soroban contract (PREIMAGE-SHA-256 settlement)
  3. WardPolicyToken Soroban contract (non-transferable coverage NFT)
  4. VaultMonitor for Horizon API SSE
  5. TypeScript SDK bindings
  6. Full test suite (unit + testnet integration)
  7. Public documentation + integration guide

Timeline: 8 weeks
Budget: $XXK (breakdown: engineering, testnet ops, audit)

Alignment: Stellar ecosystem needs institutional default protection before
serious capital can deploy into Soroban lending. Ward is that layer.
```

---

## Test Plan

- [ ] Unit (Soroban SDK): All 9 steps with mock vault/pool contracts
- [ ] Unit: `WardEscrow` — correct/wrong preimage, timing windows
- [ ] Unit: `WardPolicyToken` non-transferability (transfer panics, burn succeeds)
- [ ] Unit: Rate limiting persistent storage — 3 pass, 4th fails
- [ ] Integration: SEP-0010 auth flow on Stellar testnet
- [ ] Integration: Full claim lifecycle on Stellar testnet (Futurenet)
- [ ] Integration: VaultMonitor Horizon SSE → verified default → validate_claim
- [ ] Invariant: Ward contract holds no XLM authority, no signing keys

---

## Estimated Timeline

| Milestone | Effort |
|---|---|
| Soroban constants + primitives crate | 3 days |
| `WardPolicyToken` contract | 1 week |
| `WardClaimValidator` contract (9 steps) | 2 weeks |
| `WardEscrow` contract | 1 week |
| VaultMonitor (Horizon SSE) | 1 week |
| TypeScript SDK + Soroban bindings | 1 week |
| SEP-0010 auth integration | 3 days |
| Integration tests (Futurenet) | 1 week |
| SCF application + submission | 2 days |
| **Total** | **~8 weeks** |
