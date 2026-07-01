# Ward Protocol Invariants

This file defines the hard invariants Ward Protocol must preserve across the core protocol, SDKs, APIs, demo surfaces, and future formal specifications.

An invariant is not marketing language. It is a condition that must remain true across implementation, tests, documentation, audit evidence, and production integration.

## 1. Signer Boundary

### INV-001: Ward never signs

`ward_signed = False` is mandatory for every Ward validation, settlement, receipt, SDK response, and API response.

Ward may:

- validate ledger state
- construct unsigned transaction payloads
- return deterministic conformance results
- produce receipts
- provide rejection reasons

Ward must not:

- sign transactions
- store private keys
- request private keys
- derive signing keys
- transmit wallet seeds
- become custodian
- become counterparty
- decide settlement outside explicit ledger-state checks

### INV-002: Institutions retain signing authority

Institutional wallets, vault operators, claimants, or designated counterparties sign settlement actions. Ward returns unsigned instructions only.

### INV-003: Signing bypasses fail closed

Any request, SDK call, route, helper, demo flow, or integration path that attempts to make Ward sign must fail review, fail tests, and fail static analysis.

## 2. Ledger Authority

### INV-004: Ledger state is the source of truth

Ward decisions must be derived from authoritative ledger state. Event streams, dashboards, caches, webhooks, and pathfinding responses are hints only.

### INV-005: Server time cannot decide coverage

Coverage windows must use chain time, finalized ledger state, or an explicitly validated ledger timestamp. Server wall-clock time must not approve or reject a claim.

### INV-006: Re-reads are required for critical decisions

Critical state must be re-read before approval or settlement preparation. A previously observed event cannot be used as final authority.

## 3. Nine-Check Conformance

### INV-007: A claim cannot pass unless all nine checks pass

Ward conformance requires every check to pass. Partial success is not conformant.

### INV-008: Policy artifact must exist

The policy token, NFT, contract reference, asset, mint, or chain-native equivalent must be located before validation begins.

### INV-009: Coverage window must be active

Coverage must be active at the relevant ledger time. Expired, future, missing, or malformed coverage fails closed.

### INV-010: Vault binding must match

The policy artifact, claimant, and vault under review must refer to the same covered obligation. Cross-vault claims fail.

### INV-011: Default signal must be confirmed

Ward must confirm default state from authoritative ledger state. Event notifications alone are insufficient.

### INV-012: Loss amount must be real and bounded

Loss must be greater than zero and must be capped by explicit policy, vault, pool, and settlement rules.

### INV-013: Coverage pool must be solvent

Ward must verify pool solvency, reserve constraints, and coverage limits before producing settlement instructions.

### INV-014: Policy must still be live

Burned, closed, transferred, invalidated, settled, or replayed policy artifacts must fail validation.

### INV-015: Claimant ownership must be proven

The claimant must still control or hold the relevant policy artifact according to the selected chain primitive.

### INV-016: Signer boundary must hold at settlement

Even after all validation checks pass, Ward must only return unsigned settlement instructions.

## 4. Settlement

### INV-017: Settlement construction is idempotent

The same validated claim and ledger snapshot must produce the same unsigned settlement packet.

### INV-018: Dispute windows are deterministic

Dispute-window and timeout calculations must be expressed from ledger time or a validated chain-time value. No hidden wall-clock assumptions.

### INV-019: Settlement re-checks replay protection

Before producing unsigned settlement instructions, Ward must confirm the policy artifact has not already been settled, burned, invalidated, or replayed.

### INV-020: Settlement does not mutate validation evidence

Settlement construction must not rewrite, hide, or alter the evidence used to determine conformance.

## 5. Pathfinding and Routing

### INV-021: Pathfinding is never claim authority

XRPL pathfinding, cross-currency routing, DEX paths, AMM routes, or multi-hop settlement paths may support payment execution, but they cannot approve a claim.

### INV-022: Routes are proposals until ledger-confirmed

Route output must be treated as a proposal. Ward must verify the final payment, delivered amount, issuer, destination, and settlement result from authoritative ledger state.

### INV-023: Route-dependent values must be bounded

Slippage, transfer fees, AMM fees, trust-line quality settings, delivered amount, issuer identity, and destination constraints must be bounded before route-dependent payments are accepted as evidence.

### INV-024: No floating-point ambiguity

Route, amount, fee, and loss calculations must avoid floating-point ambiguity. Use integer, fixed-point, or precisely bounded decimal representations.

### INV-025: Untrusted route providers cannot decide outcomes

If pathfinding output comes from a server Ward does not control or trust, Ward must treat it as untrusted and compare, constrain, or independently verify the resulting ledger state.

## 6. SDK and API Boundaries

### INV-026: Private key material is forbidden

API and SDK boundaries must reject wallet seeds, private keys, mnemonic phrases, and equivalent signing secrets.

### INV-027: Inputs must be runtime validated

Addresses, policy references, NFT IDs, amounts, timestamps, condition hex values, memos, issuer references, and chain identifiers must be validated before use.

### INV-028: Unsafe defaults fail closed

Missing authentication, malformed requests, unavailable ledger reads, invalid policy references, or uncertain state must fail closed.

### INV-029: SDKs preserve the same invariant

Python, TypeScript, Rust, and future SDKs must preserve the same signer-boundary and ledger-authority invariants.

## 7. Receipts and Audit Evidence

### INV-030: Receipts must be reproducible

A conformance receipt must include enough evidence for engineering, risk, compliance, or audit reviewers to reproduce the result.

### INV-031: Rejection reasons must be explicit

Every failed claim path must return a deterministic reason tied to the failed check or failed boundary condition.

### INV-032: Public claims must match implementation state

Website, docs, demos, and sales materials must not claim production or mainnet readiness beyond what the implementation and deployed artifacts prove.

## 8. Enforcement Roadmap

These invariants should be enforced by:

- static checks for forbidden signing and key handling
- property-based tests for validator boundaries
- unit tests for settlement idempotency
- integration tests for receipt reproducibility
- CI checks for unsafe API inputs
- formal specifications for the nine-check validator state machine
- audit review for signer boundary and replay protection

## 9. Core Statement

Ward Protocol is conformant only when these conditions hold:

- all nine checks pass
- the decision is reproducible from ledger state
- settlement output is unsigned
- signer authority remains outside Ward
- `ward_signed = False`

Always.
