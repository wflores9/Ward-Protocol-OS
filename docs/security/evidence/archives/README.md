# Historical raw-ledger-read archives

This directory contains preserved XRPL Devnet raw-read evidence files. These are **historical records**, not proof that the corresponding ledger can still be queried from a public Devnet endpoint.

## Current verification boundaries

- The existing weekly GitHub Actions job runs `scripts/check_certificate_reproducibility.py`, which **re-queries the public Devnet RPC**. It does not currently replay these archive files.
- As of October 5, 2026, that live check returned `lgrNotFound` for all three indexed certificates. The [status file](../certificate-reproducibility-status.json) records the outcome.
- `KV-IV-2026-0712-001` has no `raw_reads_archive` in the certificate index. **Do not invent or backfill an issuance archive.**
- The September 2026 evidence archives may support future deterministic offline replay, but a successful offline replay would establish internal consistency of archived inputs and policy output, **not independent authentication of original ledger provenance**.
- References in older materials to automatic R2 archival or public byte-identical mirrors are historical design descriptions; current operation has not been verified in this audit.

Preserve source bytes, hashes, ledger indices, and dates. Do not silently change certificate outcomes. A future verifier must report offline replay and live ledger provenance as separate fields.

See [certificate index](../certificate-index.json) and [public audit register](../../../public-repository-audit-2026-10-08.md).
