# Ward Protocol — Solana Devnet Deployment

## Status: LIVE — E2E Verified

| Field | Value |
|-------|-------|
| Network | Solana Devnet |
| Address | AR4kydgJXmmppGGDS1ZDCroAP94LRRsFcw5Vf6CFTRMj |
| Date | June 2026 |

## E2E Verification Results

- Balance: 5 SOL loaded via faucet.solana.com
- Valid claim resolves: "RESOLVED: ward_signed=False"
- wardSigned = false confirmed
- Zero policy rejected at Check 1
- Null vault rejected at Check 3
- ward_signed = False maintained throughout

## Network Details

- RPC: https://api.devnet.solana.com
- Explorer: https://explorer.solana.com/?cluster=devnet
- Faucet: https://faucet.solana.com

## Core Invariant

ward_signed = False — Ward never holds keys, never co-signs, never acts as counterparty. Verified on Solana Devnet.
