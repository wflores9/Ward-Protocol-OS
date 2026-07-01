# Commit Convention

Ward's git history is public diligence material. Institutions and developers
read the log to judge engineering discipline. Every commit must read as
deliberate, institutional-grade, and technically precise — never speed-built.

## Format
<type>(<scope>): <concise imperative summary>
<why this change exists and what it does technically — 1-3 sentences>

<what it enables, prevents, or guarantees>

## Types
- **feat**     — a new capability or feature
- **fix**      — a bug fix
- **security** — a security-relevant fix or hardening
- **refactor** — code change that neither fixes a bug nor adds a feature
- **perf**     — a performance improvement
- **test**     — adding or correcting tests
- **docs**     — documentation only
- **chore**    — tooling, deps, config, housekeeping

## Scopes (Ward-specific)
`validator` · `credentials` · `settlement` · `primitives` · `pool` ·
`coverage` · `monitor` · `site` · `sdk` · `ci` · `docs`

## Rules
- Summary line: imperative mood ("add", not "added"), under ~72 chars, no period.
- Body: explain *why* and *what it guarantees*, not just *what*. Reference the
  invariant or standard where relevant (e.g. "ward_signed = False", XLS-70).
- State test impact when code changes ("5 tests, all paths covered").
- One logical change per commit. Don't bundle unrelated work.
- Author: `Will Flores <wflores@wardprotocol.org>` on all Ward commits.

## Example — institutional+dev grade
feat(validator): XLS-80 permissioned-domain eligibility gate with on-chain compliance record
Adds opt-in domain-membership verification (WARD_REQUIRE_DOMAIN) to the

eligibility pre-gate. Reads the PermissionedDomain ledger object, matches the

claimant against its AcceptedCredentials via XLS-70 verification, and records

the satisfying credential (issuer + type) and domain ID on ValidationResult.
Every approved resolution now emits a replayable, on-chain-derived compliance

record. Gate is off by default; the nine-step flow is unchanged when unset.

5 tests, all paths covered.

## Anti-pattern — never ship this
feat: domain stuff + record

fix: stuff

wip
