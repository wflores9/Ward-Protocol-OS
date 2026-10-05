# Ward Independent Verification Toolkit

## Purpose

This package gives an independent reviewer the public material needed to verify Ward resolution receipts without receiving Ward proprietary engine internals.

The reviewer should be able to validate that a receipt is schema-valid, unsigned, hash-replayable, and free of obvious secret/key material. This is receipt integrity verification: it proves the artifact was not altered after Ward produced it.

Where the workflow includes independently checkable primitive locators, the stronger review is decision correctness verification. The reviewer re-fetches the source evidence, re-runs the receipt rule bundle, and compares the independently derived decision against Ward's stated decision. The principle: never trust a claimed status when the primitive source can be re-derived.

This is not a production SLA, custody review, or insurance certification.

## Included Artifacts

- Receipt schema: `schemas/ward-resolution-receipt-v1.schema.json`
- Verification manifest: `docs/security/evidence/verification-manifest.json`
- Conditional-release golden receipt: `docs/security/evidence/conditional-release-golden-receipt.json`
- Netten escrow-release golden receipt: `docs/security/evidence/netten-escrow-release-golden-receipt.json`
- Live ledger case smoke evidence: `docs/security/evidence/ledger-resolution-case-smoke-2026-07-27.md`
- Verifier script: `scripts/verify_resolution_receipt.py`
- Review checklist: `docs/security/pilot-review-checklist.md`

## Setup

Python 3.10 or newer. The receipt verifier needs one package:

```bash
python3 -m pip install "jsonschema>=4.17,<5"
```

The Devnet re-derivation and archive re-proof scripts below use only the
Python standard library and run offline.

## Verify A Receipt

```bash
python3 scripts/verify_resolution_receipt.py \
  docs/security/evidence/conditional-release-golden-receipt.json

python3 scripts/verify_resolution_receipt.py \
  docs/security/evidence/netten-escrow-release-golden-receipt.json
```

Expected result:

- `ok: true`
- `hash_matches: true`
- `ward_signed: false`
- `schema: schemas/ward-resolution-receipt-v1.schema.json`

## Canonical Hash Rule

Ward receipt hash v1 is SHA-256 over Ward canonical JSON for the receipt payload after removing derived fields:

- remove `receipt_id`
- remove `receipt_hash`
- sort object keys
- use compact JSON separators
- reject unsupported JSON values such as NaN or infinity

The derived receipt ID must equal:

```text
wr_ + first 24 hex characters of receipt_hash
```

## Verification Levels

### Level 1 - Receipt Integrity

- Validate the receipt schema.
- Confirm `ward_signed` is false.
- Recompute the canonical receipt hash.
- Confirm no private key, seed, mnemonic, password, token, API key, or signature material is present.
- Confirm tampering changes the receipt hash.

### Level 2 - Decision Correctness

Only available when source evidence is independently retrievable.

- Read the receipt evidence array and rule bundle.
- Re-fetch source evidence from primitive locators such as XRPL ledger index, ledger hash, transaction hash, object ID, endpoint, and finality state.
- Re-run the same rule checks against the fetched source evidence.
- Compare the independently derived decision with Ward's receipt decision.
- Record any source that cannot be independently re-fetched as an explicit limitation.

## Review Boundary

The reviewer should explicitly check:

- Ward does not sign.
- Ward does not include private keys, seeds, mnemonics, passwords, tokens, API keys, or signatures in receipts.
- Replay of the same receipt payload produces the same hash.
- Tampering with receipt facts, checks, evidence, or unsigned actions changes the hash.
- Rejected receipts do not contain unsigned actions.
- The generic receipt model is not dependent on XLS-66, insurance, premium, coverage, or policy-NFT assumptions.

## Out Of Scope

- Production legal assurance.
- Custody, signing, settlement, or funds movement.
- Partner-sensitive data.
- Private Ward orchestration internals.
- A claim that any workflow is safe, approved, or legally enforceable.

## Reviewer Deliverable

Preferred deliverable is a short independent verification report with:

- scope and limits
- materials reviewed
- reproduction commands
- findings by severity
- explicit pass/fail/limitation statement for the receipt boundary

## Re-Derive XRPL Devnet Evidence (Offline)

The certificate evidence under `docs/security/evidence/devnet/` can be re-derived
without network access. `--verifier-role` is required: `operator` when Ward runs
it (always `independently_verified: false`), `independent` for a third party.

```bash
python3 scripts/verify_devnet_evidence_independent.py \
  docs/security/evidence/devnet/2026-09-02/phase1-devnet-pre-resolution-2026-09-02.json \
  docs/security/evidence/devnet/2026-09-02/ward-evidence-pre-resolution-2026-09-02.json \
  --verifier-role independent
```

Exit status is 0 when `failures` is empty. The role is a self-declaration by
whoever runs the script; it is recorded, not proven.

## Re-Prove Certificates From Archived Raw Reads (Offline)

Public XRPL Devnet keeps only recent ledger history, so pinned certificate
ledgers eventually stop being queryable from public RPC. Certificates issued
with a raw-reads archive are re-proved from `docs/security/evidence/archives/`:

```bash
python3 scripts/check_certificate_reproducibility.py \
  --status /tmp/ward-certificate-status.json \
  --fail-on-unreproducible --fail-on-check-error
```

Expected today: `WARD-DEVNET-20260901-001` and `WARD-DEVNET-20260902-001`
reproducible; `KV-IV-2026-0712-001` unreproducible/legacy (issued before
archive-on-issuance; no archive exists). This check confirms the archive's
pinned SHA-256, completeness, and the transaction hashes and ledger indexes it
records. It is not a cryptographic proof against ledger headers; it shows the
archived reads are the ones pinned at issuance.
