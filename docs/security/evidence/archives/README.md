# Raw-read archive store

Issuance persists a complete `ward-raw-ledger-reads/v1` document here (and as a sidecar next to the evidence bundle). The weekly job in `.github/workflows/verify-certificates-weekly.yml` re-proves certificates from these files.

It does **not** re-query public Devnet RPC. Public history expires (`lgrNotFound`).

Durable layout:

- Repo path: `docs/security/evidence/archives/<bundle-stem>.raw-reads.json`
- Public path: `/evidence/archives/<bundle-stem>.raw-reads.json` (byte-identical copy under `public/evidence/archives/` so a stranger can download without git)
- R2 binding: `EVIDENCE_ARCHIVE`
- R2 bucket: `ward-ledger-evidence`
- R2 key: `certificates/<network>/<ledger_index>/<filename>`

A certificate without `raw_reads_archive` is unreproducible. `KV-IV-2026-0712-001` is **legacy**: `raw_reads_archive` is null, Devnet ledger 3576434 is gone from public RPC, and no archive will be fabricated.
