# Ward Protocol — Polygon Amoy Testnet Deployment

## Status: LIVE — E2E Verified

| Field | Value |
|-------|-------|
| Network | Polygon Amoy Testnet |
| Chain ID | 80002 |
| Contract | WardResolver |
| Address | 0x1C9Ca1260ffbd071E1c3a02673a9e09bE07549b3 |
| Deploy Tx | 0x2c5897f438812013826b5222d85330df89b2f229ba407f86fe3a4cc33fa8c815 |
| Date | June 2026 |

## E2E Verification Results

- wardSigned() returns false — core invariant confirmed on-chain
- Valid claim resolves: "RESOLVED: ward_signed=False"
- Zero policy rejected at Check 1
- Zero vault rejected at Check 3
- ward_signed = False maintained throughout

## Explorer

https://amoy.polygonscan.com/address/0x1C9Ca1260ffbd071E1c3a02673a9e09bE07549b3

## Core Invariant

ward_signed = False — Ward never holds keys, never co-signs, never acts as counterparty. Verified on Polygon Amoy.
