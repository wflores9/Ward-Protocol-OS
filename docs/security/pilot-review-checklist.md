# Ward Pilot Security Review

## Scope
- `ward/resolution.py`
- `ward/workflows/conditional_release.py`
- `schemas/ward-resolution-receipt-v1.schema.json`
- `scripts/run_conditional_release.py`
- `src/lib/ward/apiSecurity.ts`
- `src/app/api/ledger/cases/[id]/route.ts`
- Evidence Snapshot ingestion and adapter boundary

## Trust Boundary
- Ward reads authoritative facts.
- Ward evaluates fixed rules.
- Ward produces evidence and unsigned actions.
- The institution retains signing and settlement authority.
- Ward never stores signing keys, signs, submits, or settles.

## Required Review Cases
- Canonical receipt serialization
- Receipt hash and derived-field handling
- Replay with identical inputs
- Hash change after fact mutation
- Missing evidence
- Conflicting evidence
- Failed rule evaluation
- Rejected receipt action suppression
- Signer mismatch
- Rail mismatch
- Action-type mismatch
- Signature and private-key material rejection
- Malformed JSON and unsupported values
- XLS-66 adapter isolation
- Evidence Snapshot schema and adapter contract
- Adapter ingestion token enforcement
- Oversized Evidence Snapshot rejection
- Anonymous snapshot submission rejection

## Release Blockers
- Any signed output
- Any secret or key material in a receipt
- Non-deterministic replay
- Evidence mismatch accepted
- Rejected receipt containing actions
- Missing schema validation
- Production SLA offered before independent review

## Evidence To Attach
- Focused pytest output
- Golden receipt JSON
- Independent hash verification output
- Dependency audit
- Evidence Snapshot ingestion smoke output
- Netten adapter fixture and review packet
- Reviewer findings and disposition
