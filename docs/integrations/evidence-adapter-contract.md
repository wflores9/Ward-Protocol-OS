# Ward Evidence Adapter Contract

Ward integrates clients through evidence adapters. An adapter does not decide a resolution outcome. It normalizes a client system, ledger, indexer, API, document store, or database observation into a canonical Evidence Snapshot that Ward can evaluate, replay, and include in a trust asset.

Flow:
Client system / ledger / indexer -> Evidence adapter -> ward-evidence-snapshot/v1 -> Resolution case / receipt / replay / trust asset

## Required Snapshot Fields

Every adapter output must provide:

- id: stable snapshot identifier.
- schema: ward-evidence-snapshot/v1.
- kind: broad evidence category.
- evidenceType: workflow-specific evidence type.
- label: operator-readable label.
- source: source system name.
- capturedAt: ISO timestamp when Ward captured or accepted the snapshot.
- replayStatus: not_run, matched, or mismatch.
- data: normalized business evidence.

Recommended fields:

- sourceDetails: source system, adapter, adapter version, endpoint, retrieval time.
- observation: source reference, finality, and normalized payload.
- integrity: canonicalization method, payload hash, and snapshot hash.
- canonicalHash: short integration-era hash field for compatibility with existing cases.

## Adapter Rules

- The adapter may normalize evidence.
- The adapter must not decide whether a release, default, liquidation, dispute, review, or settlement should happen.
- The adapter must not include private keys, wallet seeds, mnemonics, passwords, API keys, tokens, signing material, or secrets.
- The adapter must preserve the signer boundary. Ward may prepare unsigned instructions; the institution or protocol signer remains responsible for signing and execution.
- Source attestation is not business evidence. A Clio, rippled, indexer, or API health snapshot proves source context, not that the governed event occurred.
- Business evidence must be represented as a governed snapshot such as escrow.release, policy.artifact, trigger.event, or institution.payload.

## First Adapter Targets

1. escrow.release for Netten-style conditional service escrow.
2. receivables.resolution for Fundora-style creator receivables review.
3. source.attestation for XRPL/Clio/indexer provenance.

## Schema

The canonical schema is stored at schemas/ward-evidence-snapshot-v1.schema.json.

Client integration repos should treat this schema as the boundary contract. They can build any internal adapter they want as long as the adapter emits this snapshot shape without key material and with enough source detail for replay.
