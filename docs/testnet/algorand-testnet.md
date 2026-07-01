# Ward Protocol — Algorand Testnet Deployment

## Status: LIVE — E2E Verified

| Field | Value |
|-------|-------|
| Network | Algorand Testnet |
| Address | EXENEGR6U6Z2SWBKT5QRSLDIQYE5LGRKFVPBF4YLYVFKPC572LKPVBTSSQ |
| Date | June 2026 |

## E2E Verification Results

- Balance: 10 ALGO loaded via Dispenser
- Valid claim resolves: "RESOLVED: ward_signed=False"
- wardSigned = false confirmed
- Zero policy rejected at Check 1
- Null vault rejected at Check 3
- ward_signed = False maintained throughout

## Network Details

- Algod: https://testnet-api.algonode.cloud
- Explorer: https://testnet.algoexplorer.io
- Dispenser: https://dispenser.testnet.aws.algodev.network

## Core Invariant

ward_signed = False — Ward never holds keys, never co-signs, never acts as counterparty. Verified on Algorand Testnet.
