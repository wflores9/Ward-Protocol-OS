# Partner Verification Guide

This guide lets a reviewer reproduce Ward's current repository evidence. It
does not prove an XLS-66 mainnet deployment or a completed external audit.

## 1. Pin the Review

Record the commit before running commands:

```bash
git rev-parse HEAD
git status --short
```

The worktree must be clean for a release review.

## 2. Python Validation and Coverage

```bash
python -m pip install -e ".[dev]" "starlette>=1.2.0" "fastapi>=0.136.0"
pytest tests/ -v -m "not integration" --tb=short --cov=ward --cov-report=term-missing
cd sdk/python && pytest tests/ -v --tb=short
```

## 3. Static and Security Checks

```bash
ruff check ward/ --select=E,F,W,I --ignore=E501
ruff format ward/ --check
mypy ward/ --ignore-missing-imports
bandit -r ward/ -ll -q
python scripts/check_signing_boundary.py
pip-audit
```

## 4. Rust

```bash
cd ward
cargo test --all-features
cargo clippy --all-targets --all-features -- -D warnings
cargo audit
```

## 5. TypeScript SDK and Website

```bash
cd sdk/typescript
npm ci
npm run lint
npm test
npm audit --audit-level=moderate

cd ../..
npm ci
npm run build
npm audit --audit-level=moderate
```

## 6. TLA+ Scope

CI runs TLC against `docs/formal/ward_validator.tla` and
`docs/formal/ward_validator.cfg`. The current model-checking claim is limited to
INV-007 and INV-016. It is not a proof of every invariant in `INVARIANTS.md`.

## 7. Current Ledger Evidence Boundary

- Hosted XRPL Altnet evidence: F01-F03 policy flow
- Full XLS-65/66 lifecycle: pending XRPL Devnet integration
- Non-XRPL adapters: source scaffolds, excluded from deployable claims
- Mainnet default resolution: blocked on XLS-66 amendment and release readiness

Any pilot result should include the commit, network, ledger/object identifiers,
input values, per-check result, rejection reason, and `ward_signed = False`.

## 8. Design-Partner Evidence Bundles

For XRPL Devnet design-partner pilots, reviewers should require a JSON evidence
bundle and run the offline structural gate before reviewing the ledger objects:

```bash
python scripts/validate_partner_evidence.py path/to/evidence.json
```

The bundle shape and acceptance criteria are documented in
`docs/pilots/xrpl-devnet-lifecycle-pilot.md`. This gate does not replace ledger
replay; it prevents obvious diligence failures such as simulated results,
missing check outcomes, leaked secrets, or any claim that Ward signed.

The Ward-side semantic rule definitions are published in
`docs/pilots/ward-semantic-check-rules.md`. Reviewers should use that document
to distinguish ledger facts they can recompute directly from Ward policy
semantics such as premium memo binding, rate limits, reserve-adjusted pool
solvency, and `ward_signed = False`.

## 9. Independent XRPL Devnet Verification

Kairo/HGC independently recomputed Ward's July 2026 XRPL Devnet run from raw
ledger state without trusting Ward's validator output.

The public packet is documented in
`docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md`.

Current independent result:

- 9 of 9 Ward semantic checks independently recomputed against Ward's published
  rules.
- 0 failures.
- XRPL Devnet only, not production/mainnet.
- `ward_signed = False`.
- Not a security audit or investment endorsement.
- Residual: check-9 rate-limit history requires claim-attempt history; the
  coverage-ratio solvency portion of check 9 was independently verified.

This proof should be used as the design-partner trust anchor. A mainnet
certificate still requires XLS-65/66 mainnet readiness, completed rate-limit
history, explicit ledger/object IDs, and independent replay against production
ledger state.
