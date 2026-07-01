# Ward Protocol — Stellar Testnet Deployment

## Status: LIVE — E2E Verified

| Field | Value |
|-------|-------|
| Network | Stellar Testnet |
| Deployer | GBNIQYYVJTCWI67KHPQH5HZUAEPURXKS7XOBGLSS5WGUHVQXNT6RZGTF |
| Friendbot Tx | 4b655c2bd423717cd24c217e27dc9b2a5bf0006cbc9ddafdf04b18244514bd9f |
| Date | June 2026 |

## E2E Verification Results

- Balance: 10,000 XLM loaded via Friendbot
- Valid claim resolves: "RESOLVED: ward_signed=False"
- wardSigned = false confirmed
- Zero policy rejected at Check 1
- Null vault rejected at Check 3
- ward_signed = False maintained throughout

## Network Details

- Horizon: https://horizon-testnet.stellar.org
- Network Passphrase: Test SDF Network ; September 2015
- Explorer: https://stellar.expert/explorer/testnet

## Core Invariant

ward_signed = False — Ward never holds keys, never co-signs, never acts as counterparty. Verified on Stellar Testnet.
