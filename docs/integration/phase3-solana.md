# Phase 3 — Ward Protocol on Solana

**Chain:** Solana (Rust / Anchor)  
**Priority:** High — Panos (Anodos Finance) call June 12, 2026  
**Grant:** Solana Foundation — solana.org/grants  
**Status:** Planning

---

## Context

Panos at Anodos Finance is evaluating Ward Protocol as the default resolution layer for Solana-based institutional lending. The June 12 call should address:

1. How Ward sits **above** existing Solana lending protocols (Kamino, MarginFi) as a resolution layer — not a replacement
2. The `ward_signed = false` invariant in an Anchor program context
3. The Metaplex pNFT non-transferable policy certificate
4. Timeline and grant path via Solana Foundation

---

## How Ward Fits Above Existing Solana Lending

Ward is not a lending protocol — it is a default resolution layer. On Solana:

```
Kamino / MarginFi / Drift               Ward Protocol (Anchor)
──────────────────────────              ──────────────────────────────
VaultState account                  →   WardClaimValidator reads VaultState
  - collateral_amount                    via accountSubscribe or AccountInfo
  - outstanding_amount                   (same data, Ward doesn't modify it)
  - flags: DEFAULTED

BorrowPosition account              →   Ward reads position to derive
  - loan_id (Pubkey)                     vault_loss = outstanding_amount
  - vault (Pubkey)

LiquidityPool account               →   Ward reads pool token balance
  - usdc_balance                         for Step 6 + Step 9 solvency

```

Ward adds: policy NFT issuance, 9-step validation, PREIMAGE-SHA-256 escrow, NFT burn on settlement. It reads lending protocol state but never writes to it.

---

## Architecture

```
Institution (signing keypair)
        |
        v
  ward-client (Rust/TypeScript)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  WardPolicyNFT (Metaplex pNFT)                      │
  │    - Non-transferable (Programmable NFT rules)      │
  │    - Burnable by issuer on settlement               │
  │    - Metadata: vault, coverage, expiry, pool        │
  │                                                     │
  │  VaultMonitor (accountSubscribe WebSocket)          │
  │    - Subscribe to Kamino/MarginFi vault accounts    │
  │    - 3-slot confirmation window                     │
  │    - Heartbeat: 60s timeout → reconnect             │
  │                                                     │
  │  WardClaimValidator (Anchor program)                │
  │    - 9-step validation against Solana accounts      │
  │    - Reads lending protocol accounts (CPI or read)  │
  │    - Returns: approved, payout_lamports, reason     │
  │                                                     │
  │  WardEscrow (Anchor program, PREIMAGE-SHA-256)       │
  │    - SPL token escrow (USDC pool → claimant)        │
  │    - Condition: sha256(preimage) stored on-chain    │
  │    - Claimant calls finish with preimage            │
  │    - ward_signed = false — program holds no keys    │
  │                                                     │
  └─────────────────────────────────────────────────────┘
        |
        v
  Solana runtime / Sealevel VM
```

---

## Primitive Mapping

| Ward (XRPL Python) | Solana (Rust/Anchor) |
|---|---|
| `ClaimValidator` (Python class) | `ward_claim_validator` (Anchor program) |
| `VaultMonitor` (WebSocket + XRPL) | `accountSubscribe` WebSocket to vault accounts |
| Policy NFT (XLS-20, taxon 281) | Metaplex `pNFT` (Programmable NFT, non-transferable rule) |
| `EscrowCreate/Finish` (XRPL native) | `ward_escrow` Anchor program, SPL token escrow |
| Pool (XRPL account balance) | USDC SPL token account (ATA of pool authority) |
| `AsyncJsonRpcClient` (xrpl-py) | `solana-client` (Rust) or `@solana/web3.js` (TS) |
| `LedgerEntry(index=loan_id)` | `getAccountInfo(loanPubkey)` |
| `AccountNFTs(account=claimant)` | `getTokenAccountsByOwner` + Metaplex metadata |
| `get_ledger_close_time()` | `getClock` sysvar → `clock.unix_timestamp` |
| `XRPL_BASE_RESERVE_DROPS` | `rent.minimum_balance(size)` per account |

---

## Anchor Program Structure

```
programs/ward/
├── src/
│   ├── lib.rs              # Program entry point + instruction routing
│   ├── state/
│   │   ├── claim.rs        # ClaimRecord PDA (loan_id → validation result)
│   │   ├── escrow.rs       # EscrowRecord PDA (claim_id → escrow state)
│   │   └── rate_limit.rs   # RateLimitWindow PDA (nft_mint → timestamps)
│   ├── instructions/
│   │   ├── validate_claim.rs    # 9-step validator
│   │   ├── create_escrow.rs     # EscrowCreate equivalent
│   │   ├── finish_escrow.rs     # EscrowFinish with preimage
│   │   └── cancel_escrow.rs     # EscrowCancel
│   ├── errors.rs           # WardError enum (→ Anchor error codes)
│   └── constants.rs        # Protocol constants
├── Cargo.toml
└── tests/
    └── ward.ts             # Anchor test suite
```

---

## Step-by-Step Porting Guide

### Step 1 — Constants (`ward/constants.py` → `programs/ward/src/constants.rs`)

```rust
pub const MIN_COVERAGE_RATIO_X100: u64 = 150; // 1.5 × 100 (no floats in Solana)
pub const CLAIM_RATE_LIMIT_MAX: u64 = 3;
pub const CLAIM_RATE_LIMIT_WINDOW: i64 = 300; // seconds
pub const ESCROW_DISPUTE_SECS: i64 = 48 * 3600;
pub const ESCROW_CANCEL_SECS: i64 = 72 * 3600;
pub const DEFAULT_CONFIRM_COUNT: u64 = 3;
pub const WARD_POLICY_NFT_SYMBOL: &str = "WARD";
```

### Step 2 — Primitives (`ward/primitives.py` → `programs/ward/src/primitives.rs`)

```rust
use sha2::{Sha256, Digest};

pub fn verify_preimage(preimage: &[u8; 32], condition: &[u8; 32]) -> bool {
    let hash = Sha256::digest(preimage);
    hash.as_slice() == condition
}

// check_rate_limit() → RateLimitWindow PDA
// One PDA per nft_mint, stores Vec<i64> of timestamps
// Anchor constraint: window.timestamps.len() < CLAIM_RATE_LIMIT_MAX
```

### Step 3 — ClaimValidator (`ward/validator.py` → `instructions/validate_claim.rs`)

9 steps mapped to Anchor instruction with account validation:

```rust
#[derive(Accounts)]
pub struct ValidateClaim<'info> {
    pub claimant: Signer<'info>,

    // Step 1+7+8: Policy NFT must be non-transferable pNFT owned by claimant
    pub nft_mint: Account<'info, Mint>,
    pub nft_token_account: Account<'info, TokenAccount>,
    pub nft_metadata: Account<'info, MetadataAccount>, // Metaplex

    // Step 3: Vault binding from NFT metadata
    pub defaulted_vault: AccountInfo<'info>, // Kamino/MarginFi vault account

    // Step 4+5: Loan account from lending protocol
    pub loan_account: AccountInfo<'info>,

    // Step 6+9: Pool USDC token account
    pub pool_token_account: Account<'info, TokenAccount>,

    // Step 9: Rate limit PDA
    #[account(
        init_if_needed,
        payer = claimant,
        space = RateLimitWindow::LEN,
        seeds = [b"rate_limit", nft_mint.key().as_ref()],
        bump
    )]
    pub rate_limit: Account<'info, RateLimitWindow>,

    pub clock: Sysvar<'info, Clock>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}
```

### Step 4 — EscrowSettlement (`ward/settlement.py` → `instructions/create_escrow.rs`)

```rust
#[account]
pub struct EscrowRecord {
    pub claim_id: [u8; 32],
    pub pool: Pubkey,
    pub claimant: Pubkey,
    pub amount: u64,              // lamports or USDC base units
    pub condition: [u8; 32],      // sha256(preimage)
    pub finish_after: i64,        // clock.unix_timestamp + 48h
    pub cancel_after: i64,        // clock.unix_timestamp + 72h
    pub settled: bool,
    pub nft_mint: Pubkey,         // for burn-on-settle
    pub bump: u8,
}

// finish_escrow verifies: sha256(preimage) == record.condition
// Then: SPL transfer pool_token_account → claimant_token_account
// Then: burn the policy NFT (Metaplex burn instruction)
// ward_signed = false: pool authority signs create, claimant signs finish
```

### Step 5 — VaultMonitor (`ward/vault_monitor.py` → TypeScript client)

```typescript
import { Connection, PublicKey } from '@solana/web3.js';

const connection = new Connection(SOLANA_WS_URL, 'confirmed');
const vaultPubkey = new PublicKey(vaultAddress);

let confirmationCount = 0;

const subscriptionId = connection.onAccountChange(
  vaultPubkey,
  async (accountInfo, context) => {
    const vaultState = decodeVaultState(accountInfo.data); // Kamino layout
    if (vaultState.flags & DEFAULTED_FLAG) {
      confirmationCount++;
      if (confirmationCount >= DEFAULT_CONFIRM_COUNT) {
        await onVerifiedDefault({ vaultAddress, slotContext: context });
        confirmationCount = 0;
      }
    } else {
      confirmationCount = 0; // reset on non-default state
    }
  },
  { commitment: 'confirmed' }
);
```

Heartbeat: Solana `onAccountChange` subscriptions don't have built-in heartbeat — implement with `setInterval` + `connection.getSlot()` check, same 60s timeout logic as XRPL.

---

## Kamino/MarginFi Interface Notes

- **Kamino vault accounts** use a custom discriminator layout. Ward reads `CollateralAmount`, `LoanAmount`, and `LiquidationFlag` fields from deserialized account data. No Kamino SDK dependency required — raw account data deserialization only.
- **MarginFi** exposes `MarginfiAccount` with `active_balance` and `liquidation_threshold`. Ward Step 5 maps `active_balance - liquidation_threshold → vault_loss`.
- Ward does **not** call any Kamino/MarginFi instructions — it only reads their account state via `AccountInfo` / `getAccountInfo`. No CPI, no authority.

---

## Test Plan

- [ ] Unit (Anchor tests): All 9 steps in `validate_claim` with mock accounts
- [ ] Unit: `create_escrow`, `finish_escrow` (correct preimage), `finish_escrow` (wrong preimage → error), `cancel_escrow` (before/after window)
- [ ] Unit: `RateLimitWindow` PDA — 3 calls pass, 4th fails
- [ ] Unit: Metaplex pNFT transfer rule enforcement
- [ ] Integration: Full claim lifecycle on Solana devnet
- [ ] Integration: VaultMonitor `onAccountChange` → verified default → `validate_claim`
- [ ] Invariant: Ward program holds no SOL authority, no signing keys; pool authority is institution keypair

---

## Preparation for June 12 Call (Panos / Anodos Finance)

Key points to communicate:

1. **Ward is a layer, not a competitor** — it reads Kamino/MarginFi state, never writes to it
2. **9-step validation is auditable** — every step is an on-chain account read with a verifiable result
3. **`ward_signed = false`** — Anodos holds all signing authority; Ward program is stateless validation logic
4. **Metaplex pNFT** gives institutions a non-transferable, burnable policy certificate with on-chain metadata
5. **Timeline** — 8 weeks to devnet, pending Solana Foundation grant approval

---

## Estimated Timeline

| Milestone | Effort |
|---|---|
| Anchor program scaffold + constants | 3 days |
| `WardClaimValidator` (9 steps, Anchor) | 2 weeks |
| `WardEscrow` (SPL token, Anchor) | 1 week |
| Metaplex pNFT mint + burn flow | 1 week |
| VaultMonitor (`onAccountChange` TS) | 1 week |
| TypeScript SDK + Anchor IDL bindings | 1 week |
| Integration tests (devnet) | 1 week |
| **Total** | **~8 weeks** |

---

## Grant Reference

**Solana Foundation Grants:** solana.org/grants  
Application framing: "Ward Protocol brings deterministic default resolution to Solana institutional lending. As a pure resolution layer above Kamino/MarginFi, Ward adds auditable 9-step claim validation and PREIMAGE-SHA-256 escrow settlement — without modifying or depending on existing lending protocol logic."
