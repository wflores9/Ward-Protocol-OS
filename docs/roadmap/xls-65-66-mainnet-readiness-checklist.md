# XLS-65/66 Mainnet Readiness Checklist

Ward is pre-mainnet infrastructure for XLS-65/66-enabled institutional credit.
This checklist defines the work required before Ward should present a production
mainnet default-resolution claim.

## Scope Boundary

- Current proof: XRPL Devnet independent verification.
- Current result: 9 of 9 Ward semantic checks independently recomputed, zero
  failures.
- Current limitation: Devnet only, not production/mainnet.
- Residual: Check-9 rate-limit history requires claim-attempt history; the
  coverage-ratio solvency portion has been independently verified.

## Phase 1 - Protocol Readiness Tracking

- Track XLS-65 Single Asset Vault and XLS-66 Lending Protocol amendment status.
- Keep public copy framed as "Designed for XLS-66-enabled institutional credit."
- Do not use "live on mainnet" for XLS-66-dependent default-resolution flows
  until the required XRPL capabilities are active and Ward has passed mainnet
  evidence review.
- Maintain a changelog of amendment/API object changes that affect Ward checks.

## Phase 2 - Mainnet Adapter Finalization

- Map XLS-65 vault objects to Ward policy binding and pool solvency checks.
- Map XLS-66 Loan and LoanBroker objects to default readiness, loss math, and
  first-loss capital absorption.
- Bind each Ward semantic check to a specific ledger object, field, and rule
  version.
- Preserve `ward_signed = False`: Ward verifies and prepares evidence; the
  institution signs; the ledger settles.

## Phase 3 - Evidence and Replay Surface

- Publish a machine-readable evidence bundle for every design-partner run.
- Include network, ledger index, close time, object identifiers, input values,
  per-check status, rejection reasons, and Ward rule version.
- Persist claim-attempt history for check-9 rate-limit verification.
- Add a replay command that recomputes the result from ledger objects and the
  published Ward rule version.

## Phase 4 - Independent Mainnet Verification

- Request an unaffiliated verification pass against mainnet ledger state.
- Require the verifier to ignore Ward's validator output and recompute from raw
  ledger state.
- Bind the certificate to the exact object IDs, ledger range, rule version, and
  commit hash.
- Mark anything not publicly derivable as out of scope instead of implying it
  was verified.

## Phase 5 - Production Launch Gate

Ward should not claim production mainnet readiness until all of the following
are complete:

- Required XLS-65/66 capabilities are active on mainnet.
- A mainnet evidence bundle passes Ward validation.
- The same bundle passes independent replay.
- Check-9 rate-limit history is available and reproducible.
- An institution signs the settlement action; Ward does not sign.
- The public page states the scope, residuals, and verifier identity.

## Phase 6 - Post-XRPL Expansion

After the XLS-65/66 thesis is proven on mainnet, Ward can evaluate cross-chain
deployment paths, including Quant Overledger or other institutional routing
layers. That work should be treated as a new adapter-promotion program, not as a
current production claim.
