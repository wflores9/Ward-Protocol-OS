# Infrastructure — Historical Technical Notes

> **Status: historical / not a current production deployment declaration.**
> This document intentionally does not publish internal operational topology, deployment configuration, administrative endpoints, or a production-readiness claim.

The public Ward architecture separates:

1. **Evidence inputs** — authoritative ledger facts or independently verifiable external attestations.
2. **Deterministic evaluation** — fixed policy and canonical evidence snapshots.
3. **Unsigned receipts** — reproducible outputs with `ward_signed = false`.
4. **Institutional controls** — approval, signing, custody, and execution outside Ward.

The repository contains testnet/Devnet tooling and public schemas. These do not establish a production customer deployment or live Mainnet settlement capability.

For a review of current interfaces, start with the [repository README](../README.md), [integration index](integration/README.md), and [security policy](../SECURITY.md). Do not treat old deployment notes, historical test counts, or experimental network configurations as current operating instructions.
