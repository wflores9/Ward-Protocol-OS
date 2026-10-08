# Ward Protocol — Integration Documentation

Ward evaluates authoritative evidence against fixed, versioned institutional rules and produces an **unsigned, replayable resolution receipt**. Institutions retain responsibility for approval, signing, custody, and execution.

> **Invariant:** `ward_signed = false`. Ward evaluates. The institution signs. The ledger or other authorized system settles.

## Start here

| Document | Purpose | Status |
| --- | --- | --- |
| [Ward × Molpha: conditional escrow customer workflow](ward-molpha-conditional-escrow-customer-workflow.md) | End-to-end example for customer and technical review, from external signed evidence through policy, institutional approval, and execution. | **Proposed — not an implemented integration or partnership commitment** |
| [Signed-tuple evidence adapter specification](signed-tuple-evidence-adapter-spec.md) | Proposed signed-tuple verification inputs, evidence normalization, source identity and replay boundaries. | Specification — provider details require confirmation |
| [QuorumVault verification boundary](quorumvault-two-tier-boundary.md) | Independent receipt and source-evidence verification model, including the treatment of signed tuples. | Public technical design |

## Review path

For a first review, read the [customer workflow](ward-molpha-conditional-escrow-customer-workflow.md). For signature and field-level questions, continue to the [signed-tuple adapter specification](signed-tuple-evidence-adapter-spec.md). For independent verification and replay, use the [QuorumVault boundary](quorumvault-two-tier-boundary.md).

Relevant implementation-oriented references: [synthetic conditional-release input](../../examples/conditional-release-input.json), [resolution receipt schema](../../schemas/ward-resolution-receipt-v1.schema.json), and the [public repository overview](../../README.md).

## Scope and limitations

These documents describe designs and review proposals. They do not establish a completed Ward × Molpha integration, institutional customer, production pilot, or agreed commercial terms. A valid cryptographic attestation alone does not prove that the underlying external-world fact is true. Production use requires confirmation of source trust, exact signed-tuple contract, policy requirements, institutional controls, and supported execution capabilities.

Other experimental rail adapters and multi-chain planning documents may exist elsewhere in this public repository. They are **not part of the current integration review path**, and no network support or delivery commitment should be inferred from their presence.
