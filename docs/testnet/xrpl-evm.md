# Ward Protocol — XRPL EVM Sidechain Testnet Deployment

## Status: LIVE — E2E Verified

| Field | Value |
|-------|-------|
| Network | XRPL EVM Sidechain Testnet |
| Chain ID | 1449000 |
| Contract | WardResolver |
| Address | 0x1C9Ca1260ffbd071E1c3a02673a9e09bE07549b3 |
| Deploy Tx | 0xdaad34e8d7b3fd9f8a681cbac1f2212807573d7527903eacff618a241b60fe85 |
| Date | June 2026 |

## E2E Verification Results

- wardSigned() returns false — core invariant confirmed on-chain
- Valid claim resolves: "RESOLVED: ward_signed=False"
- Zero policy rejected at Check 1
- Zero vault rejected at Check 3
- ward_signed = False maintained throughout

## Explorer

https://explorer.testnet.xrplevm.org/address/0x1C9Ca1260ffbd071E1c3a02673a9e09bE07549b3

## Core Invariant

ward_signed = False — Ward never holds keys, never co-signs, never acts as counterparty. Verified on XRPL EVM Sidechain.
