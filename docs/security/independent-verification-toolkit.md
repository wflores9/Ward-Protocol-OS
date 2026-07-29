# Ward Independent Verification Toolkit

## Purpose

This package gives an independent reviewer the public material needed to verify Ward resolution receipts without receiving Ward proprietary engine internals.

The reviewer should be able to validate that a receipt is schema-valid, unsigned, hash-replayable, and free of obvious secret/key material. This is not a production SLA, custody review, or insurance certification.

## Included Artifacts

- Receipt schema: `schemas/ward-resolution-receipt-v1.schema.json`
- Verification manifest: `docs/security/evidence/verification-manifest.json`
- Conditional-release golden receipt: `docs/security/evidence/conditional-release-golden-receipt.json`
- Netten escrow-release golden receipt: `docs/security/evidence/netten-escrow-release-golden-receipt.json`
- Live ledger case smoke evidence: `docs/security/evidence/ledger-resolution-case-smoke-2026-07-27.md`
- Verifier script: `scripts/verify_resolution_receipt.py`
- Review checklist: `docs/security/pilot-review-checklist.md`

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
