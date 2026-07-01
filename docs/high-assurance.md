# Ward Protocol High-Assurance Architecture

## "Fortress Code" Standard

Ward Protocol is designed as high-assurance deterministic infrastructure for tokenized credit. The engineering standard is modeled after the rigor expected in nuclear power systems, avionics, military systems, and other safety-critical environments where outcomes must be predictable, reviewable, and constrained by explicit invariants.

This document defines the high-assurance architecture posture for Ward Protocol and the implementation path required to make that posture enforceable in code, tests, audits, and future formal specifications.

## Core Principles

### Determinism by Design

Every Ward outcome must be mathematically predictable from authoritative ledger state only. The protocol must not depend on discretionary operators, mutable dashboards, subjective review, server clocks, or hidden off-chain state to decide whether a claim is conformant.

Required properties:

- The same ledger state must always produce the same validation result.
- Event streams may be used as hints, but final decisions must come from authoritative ledger reads.
- Rejection reasons must be explicit, inspectable, and reproducible.
- Conformance receipts must map directly to the evidence used by the validator.

### Zero Trust and Separation of Privilege

`ward_signed = False` is a hard architectural invariant. Ward validates, prepares, and reports. Institutions sign. The chain settles. Ward must never become a custodian, counterparty, transaction signer, or discretionary settlement authority.

Required properties:

- Ward must never store, request, derive, or transmit private keys or wallet seeds.
- All settlement transactions produced by Ward must be unsigned by default.
- Signing authority must remain with the institution, vault operator, claimant, or designated counterparty.
- Any code path that implies Ward signing must fail review, fail tests, and fail static analysis.

### Formal Methods Ready

Critical Ward paths must be structured so they can later be modeled in TLA+, Coq, Lean, or equivalent formal verification systems. The current implementation should be written in a way that keeps invariants explicit and state transitions simple enough to reason about.

Required properties:

- Validator state transitions must be explicit and finite.
- Critical functions should be pure where possible.
- Side effects must be isolated to explicit ledger reads, transaction construction, or API boundary handling.
- Key invariants must be documented near the code they protect and in shared architecture documents.

### Defense in Depth

Ward should not rely on a single check, control, cache, service, or operator assumption. Every critical path should be protected by multiple independent validation layers.

Required properties:

- The validator must use all nine checks before returning a conformant claim.
- Settlement construction must re-check critical safety conditions before producing unsigned instructions.
- Rate limits, replay protection, solvency checks, and signer-boundary checks must operate independently.
- Unsafe defaults must fail closed.

### Algorithmic Rigor and Formal Methods

Ward should prefer algorithms and protocol integrations with clear mathematical properties, deterministic behavior, and reviewable failure modes. Routing, payment, and settlement-support logic must be treated with the same rigor as claim validation.

XRPL pathfinding is relevant for premium payments, collateral movement, and multi-asset settlement support, but it must not become claim-decision authority. The XRPL `path_find` and `ripple_path_find` APIs can return possible payment paths, but pathfinding results can become stale, may not be globally optimal, and must be treated carefully when returned by untrusted servers.

Required properties:

- Pathfinding output is a route proposal, not an authoritative Ward decision.
- Ward must never sign automatically because a path was found.
- Ward must verify the final payment or settlement result from authoritative ledger state.
- Path-related validation must be deterministic, free of floating-point ambiguity, and reproducible from receipt evidence.
- Critical route assumptions should be covered by property-based tests and, where feasible, formal specification.
- Integrations should compare or constrain pathfinding output when route quality, cost, issuer, or liquidity source matters to institutional risk.

Target invariants:

- A route can support a transaction, but it cannot approve a claim.
- Claim conformance still requires all nine Ward checks.
- Premium or settlement payment status must be proven by ledger state, not by a pathfinding response.
- Slippage, fees, delivered amount, issuer, and destination must be bounded before a route-dependent payment is considered acceptable.

## Priority Module Improvements

### 1. Validator and Resolver

The validator and resolver are the highest-assurance components in Ward because they define whether a claim is conformant. These modules should be treated as the first formal-verification target.

Required improvements:

- Add formal invariants for all nine checks.
- Add runtime property checks on every authoritative ledger read.
- Keep validation functions pure wherever possible.
- Treat event input as non-authoritative until re-verified from ledger state.
- Return structured rejection reasons for every failed check.
- Make every validation result reproducible from the receipt evidence.

Target invariants:

- A claim cannot pass unless all nine checks pass.
- A policy artifact must exist before validation begins.
- Coverage must be evaluated using chain time or finalized ledger state.
- Vault binding must match the policy reference and defaulted vault.
- Default state must be confirmed from authoritative ledger state.
- Loss amount must be positive and bounded.
- Coverage pool solvency must hold before settlement preparation.
- Policy artifact must still be live.
- Claimant ownership must be proven.
- Ward must return unsigned settlement instructions only.

### 2. Settlement Engine

The settlement engine must be deterministic, idempotent, and timeout-safe. It is responsible for constructing the unsigned packet that the institution reviews and signs.

Required improvements:

- Escrow creation and finish paths must be idempotent.
- Timeout and dispute-window calculations must be expressed as explicit formulas.
- Settlement construction must not mutate validation state.
- Settlement output must preserve `ward_signed = False`.
- Replay protection must be re-checked before settlement construction.
- Mathematical assumptions for dispute windows should be documented in code comments and tests.

Target invariants:

- Ward never signs EscrowCreate, EscrowFinish, burn, payout, or equivalent settlement actions.
- The same validated claim and ledger snapshot must produce the same unsigned settlement packet.
- Dispute-window timing must be deterministic from ledger time or an explicitly provided chain time value.
- Settlement must not proceed if the policy has already been burned, settled, invalidated, or replayed.

### 3. Client and Transaction Builder

The client and transaction builder define the integration boundary between Ward and institutional systems. This boundary must be strongly typed, validated, and unsigned by default.

Required improvements:

- All transactions must be unsigned by default.
- All address, amount, condition, memo, and policy references must be runtime validated.
- Wallet seeds and private keys must be rejected at API boundaries.
- Transaction builders must return explicit unsigned payloads.
- TypeScript, Python, and Rust SDK surfaces should preserve the same signer-boundary invariant.

Target invariants:

- No SDK method may require a private key to validate a claim.
- No SDK method may sign a settlement action on behalf of Ward.
- Transaction builders must make the signing boundary visible to integrators.
- Invalid addresses, negative amounts, malformed conditions, and unsafe memo payloads must fail closed.

## High-Assurance Checklist

### Phase 1: Immediate - This Week

- [ ] Enforce `ward_signed = False` with static analysis or a linter rule.
- [ ] Add property-based testing with Hypothesis for all nine checks.
- [ ] Document hard invariants in code comments and a separate `INVARIANTS.md`.
- [ ] Run the full test suite with coverage above 85 percent on critical paths.
- [ ] Add formal specification comments for validator, resolver, settlement, and transaction-builder functions.
- [ ] Add CI checks that fail on forbidden signing, seed handling, or unsafe settlement patterns.
- [ ] Confirm all conformance receipts include enough evidence to reproduce the result.

### Phase 2: Next 30 Days

- [ ] Introduce formal verification for the validator core, starting with TLA+.
- [ ] Define the nine-check state machine in a formal or semi-formal specification.
- [ ] Add reproducible build requirements for release artifacts.
- [ ] Prepare independent security audit scope and Code4rena-ready documentation.
- [ ] Expand Rust coverage for memory-safe critical-path components where appropriate.
- [ ] Add property tests for settlement idempotency, replay protection, and dispute-window math.

### Phase 3: Ongoing

- [ ] Produce a full mathematical proof of nine-check determinism.
- [ ] Submit critical paths for third-party high-assurance review.
- [ ] Maintain a public conformance registry tied to reproducible receipts.
- [ ] Keep all SDKs aligned with the same signer-boundary invariant.
- [ ] Track every high-assurance invariant as code, tests, documentation, and audit evidence.

## Public Trust Posture

The public site should describe Ward as high-assurance deterministic infrastructure for tokenized credit. The repository must prove that statement through enforceable artifacts:

- `HIGH_ASSURANCE.md`
- `INVARIANTS.md`
- property-based tests
- static signing-boundary checks
- reproducible receipts
- audit-ready documentation
- formal-methods-ready validator design

Ward should never rely on language alone. The standard is only credible when the codebase, tests, documentation, and integration surfaces all prove the same thing:

`ward_signed = False`

Always.
