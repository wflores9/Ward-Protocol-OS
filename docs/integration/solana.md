# Solana — Ward Protocol Integration Guide

## Overview

Solana is a high-throughput Layer 1 blockchain using a Proof-of-History consensus mechanism. Ward Protocol integrates Solana via `SolanaAdapter`, which reads SPL token account state natively and builds unsigned SPL token transfer instructions for RLUSD resolution settlements.

Ward policy NFTs on Solana are Metaplex NFTs with a Ward taxon attribute. Pool accounts are standard SPL token accounts holding RLUSD.

## Solana Key Facts

| Property | Value |
|---|---|
| Consensus | Proof-of-History + Tower BFT |
| Native token | SOL |
| RLUSD | SPL token (mint address published at XLS-66 mainnet) |
| Finality | ~400ms (optimistic) / ~2.5s (finalized) |
| RPC (Mainnet) | `https://api.mainnet-beta.solana.com` |
| RPC (Devnet) | `https://api.devnet.solana.com` |
| Explorer | `https://explorer.solana.com` |

## SolanaAdapter Architecture

`SolanaAdapter` extends `ChainAdapter` and targets the Solana JSON-RPC API.

```python
from ward.adapters import SolanaAdapter

adapter = SolanaAdapter(
    rpc_url="https://api.mainnet-beta.solana.com",
    rlusd_mint="<RLUSD SPL mint address>",
    commitment="finalized",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read Metaplex NFT + SPL pool token balance |
| `get_ledger_state()` | Fetch slot, blockhash, clock sysvar |
| `build_resolution_tx()` | Produce unsigned SPL transfer instruction |

### SPL Token Transfer (unsigned)

```python
tx = await adapter.build_resolution_tx(
    pool_token_account="<pool SPL token account>",
    claimant_token_account="<claimant SPL token account>",
    authority_address="<pool authority pubkey>",
    payout_amount=500_000_000,  # in SPL base units
    recent_blockhash="<from getLatestBlockhash>",
    nonce=0,
)
assert tx.ward_signed is False  # invariant
```

## Resolution Flow

```
1. Ward oracle reads XRPL ledger state (vault default, pool balance)
        │
        ▼
2. Oracle writes verified state to Ward Solana program
   (registerPolicy, recordDefault, setPoolBalance)
        │
        ▼
3. Institution calls Ward program checkClaim — nine checks run on-chain
        │
        ▼
4. Program returns unsigned SPL transfer instruction
   (ward_signed = false always)
        │
        ▼
5. Institution signs transaction with their keypair
        │
        ▼
6. Solana runtime settles — RLUSD transferred, NFT burned for replay protection
```

## Ward Solana Program (Planned)

The Solana port of WardResolver is a native Rust program:

```rust
pub fn resolve_claim_unsigned(
    ctx: Context<ResolveClaim>,
    claim: ClaimInput,
) -> Result<ResolutionResult> {
    // Nine on-chain checks
    // ward_signed = false — always
    // Returns unsigned transfer instruction
}
```

Mirrors the nine checks of `WardResolver.sol` using Solana account data.

## Security Notes

- `ward_signed = False` — institution signs with their Ed25519 keypair
- `commitment="finalized"` required for Step 2 (ledger time) — never use `processed`
- SPL token transfers require recent blockhash — always fetch fresh from RPC
- Replay protection: Ward program tracks burned NFT mint addresses

## Status

Implemented in `ward/adapters/solana.py`. Solana program (Rust) and RLUSD SPL mint pending Ripple mainnet deployment.
