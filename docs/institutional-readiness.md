# Institutional Readiness Controls

## Core invariant

`ward_signed = false` is a hard invariant across the repository. Ward prepares unsigned payloads only. Institutions sign. Chains settle.

## Controls added in this hardening pass

### 1. Premium-payment verification is fail-closed

Claim validation now requires an on-chain premium `Payment` on the pool account that matches:

- claimant address
- destination pool address
- policy NFT token id
- coverage amount encoded in `ward/policy-premium`

Claims without that payment are rejected.

### 2. Multi-chain adapters no longer accept placeholder asset routing config

The following constructor defaults are now blocked for production use:

- Solana RLUSD mint placeholder
- Stellar RLUSD issuer placeholder
- Flare RLUSD zero address
- Hedera RLUSD token id `0.0.0`
- Axelar gateway zero address
- XDC RLUSD zero address

These values were left in the repository only as historical documentation of non-production scaffolding. Runtime acceptance was removed because institutional deployments must fail closed instead of silently building invalid settlement payloads.

### 3. XRPL client lifecycle is version-tolerant

Core XRPL modules now use a shared client context wrapper so they behave safely across xrpl-py releases and test mocks without mutating client classes at runtime.

## Non-production surfaces intentionally retained

The following paths remain in the repository but are not part of the institutional production surface:

- `starter/`
- `demo/`
- `docs/testnet/`

They are retained for developer onboarding, testnet demonstrations, and specification walkthroughs. They must not be used as deployment authority or operational runbooks for regulated production environments.
