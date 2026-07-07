# XRPL Devnet Lifecycle Pilot

This is the step-by-step path for proving Ward's first thesis before any
mainnet or multi-chain production claim:

> A default can be resolved deterministically from ledger state, with Ward never
> signing or deciding the outcome.

## Status

- Current hosted evidence: XRPL Altnet F01-F03 policy verification
- Next proof target: XRPL Devnet XLS-65/66 lifecycle validation
- Mainnet default resolution: pending XLS-66 amendment and release readiness
- Non-XRPL adapters: scaffolded only, excluded from this pilot

## Roles

| Role | Responsibility |
| --- | --- |
| Design partner | Creates or exports the Devnet vault, broker, loan, and default identifiers |
| Ward | Reads those identifiers, runs the nine checks, and returns an evidence bundle |
| Institution/operator | Reviews and signs any settlement instruction outside Ward |
| Reviewer | Re-runs the bundle validation and reproduces the claim from the same ledger state |

## Phase 1 — Produce Devnet Ground Truth

1. Use an independent XLS-65/66 Devnet flow to create the lending objects.
2. Record the Devnet RPC endpoint.
3. Record the final ledger index used for validation.
4. Mint a Ward policy NFT and pay the Ward policy-premium memo to the pool wallet.
5. Export the Vault ID, LoanBroker ID, Loan ID, policy NFT, claimant, pool, and defaulted vault.
6. Export every transaction hash that created, funded, impaired, defaulted, or settled the loan.
7. Do not export seeds, private keys, mnemonics, or wallet files.

For Ward validation, stop before the default-resolution transaction clears the
positive loss fields:

```bash
python scripts/phase1_devnet_xls6566.py \
  --out evidence/devnet/phase1-devnet-pre-resolution.json \
  --stop-before-default-resolution
```

This waits through the payment interval plus grace window, captures
`Loan_pre_default_resolution`, and exits before `LoanManageRetryAfterGrace`.

Acceptable references include:

- `https://lending-test-lovat.vercel.app/`
- `https://flow.blockcelerate.net/`
- `https://lending.xls-demo.com/`

These are unaffiliated behavioral references. Do not copy unlicensed source.

## Phase 2 — Run Ward Against the Same Ledger State

The Ward run must use the same network and object identifiers supplied by the
partner. It must not generate a simulated result if Devnet is unavailable.

Lifecycle-only output can be converted into a fail-closed Ward evidence bundle:

```bash
python scripts/run_xrpl_devnet_evidence.py \
  evidence/devnet/phase1-devnet-run-2026-07-06-150s.json \
  --out evidence/devnet/ward-evidence-2026-07-06.json \
  --query-devnet \
  --allow-incomplete
```

`--allow-incomplete` is intentionally explicit. Without a Ward policy NFT,
pool address, claimant, and vault binding, the runner rejects at Step 1 and does
not produce an approval or settlement packet.

Once a partner provides the Ward policy inputs, run without
`--allow-incomplete`. This invokes Ward's canonical validator against XRPL
Devnet JSON-RPC and maps the validator result into the evidence bundle:

```bash
python scripts/run_xrpl_devnet_evidence.py \
  evidence/devnet/phase1-devnet-run-2026-07-06-150s.json \
  --out evidence/devnet/ward-evidence-2026-07-06.json \
  --query-devnet \
  --xrpl-json-rpc-url "https://s.devnet.rippletest.net:51234"
```

If the lifecycle artifact was produced by the current script, it includes a
`ward_policy` block with the policy NFT, pool, claimant, and covered vault.
Override flags (`--policy-nft-id`, `--pool-address`, `--claimant-address`,
`--defaulted-vault`) are still available for partner-supplied artifacts.

The 2026-07-07 Devnet run minted a real Ward policy NFT, paid the premium memo,
and let canonical Ward validation pass Steps 1-4. The run rejected at Step 5
because validation occurred after `LoanManage` cleared the positive loss fields,
leaving `loss_drops = 0`. The next full-approval run must capture or validate at
the pre-default-resolution point where the positive loss is still visible on
ledger.

Ward treats that pre-resolution point as default-ready only when ledger time has
passed `NextPaymentDueDate + GracePeriod` and the loan still has positive
outstanding value. It does not approve early claims before the grace window.

Required Ward output:

- commit hash
- network name and RPC URL
- ledger index
- all input identifiers
- nine check outcomes
- rejection reason when rejected
- approved flag
- settlement metadata, if eligible
- `ward_signed = False`

## Phase 3 — Validate the Evidence Bundle

Save the Ward output as JSON and run:

```bash
python scripts/validate_partner_evidence.py path/to/evidence.json
```

The validator rejects bundles that:

- contain seed, secret, private-key, mnemonic, or passphrase fields
- contain simulated, mock, fake, placeholder, or dummy language
- omit any of the nine checks
- claim `ward_signed = True`
- omit ledger or transaction identifiers
- use a network other than XRPL Devnet for this pilot

## Evidence Bundle Shape

```json
{
  "protocol": "Ward Protocol",
  "evidence_type": "xrpl-devnet-lifecycle",
  "generated_at": "ISO-8601 timestamp",
  "commit": "git commit hash",
  "network": {
    "name": "XRPL Devnet",
    "rpc_url": "wss://s.devnet.rippletest.net:51233",
    "ledger_index": 0
  },
  "source": {
    "tool": "name of partner or reference flow",
    "unaffiliated_reference": true
  },
  "objects": {
    "vault_id": "ledger object id",
    "loan_broker_id": "ledger object id",
    "loan_id": "ledger object id",
    "policy_nft_id": "NFTokenID",
    "pool_address": "XRPL account",
    "claimant_address": "XRPL account",
    "defaulted_vault": "XRPL account or object binding"
  },
  "transactions": [
    {
      "hash": "transaction hash",
      "type": "transaction type",
      "ledger_index": 0
    }
  ],
  "ward_result": {
    "ward_signed": false,
    "approved": false,
    "steps_passed": 0,
    "rejection_reason": "",
    "checks": [
      {
        "number": 1,
        "label": "Policy NFT located",
        "status": "passed"
      }
    ],
    "settlement": {
      "unsigned_packet_present": false,
      "signed_by_ward": false
    }
  }
}
```

The real bundle must contain checks 1 through 9 exactly once.

## Passing Gate

The pilot is evidence-complete only when an independent reviewer can:

1. Re-run the bundle validator.
2. Query the same Devnet objects.
3. Reproduce the same nine check outcomes.
4. Confirm no Ward key or signing operation exists in the flow.
5. Explain why approval or rejection followed deterministically from ledger state.

Until then, the result is an integration exercise, not production readiness.

## 2026-07-07 Policy Artifact Run

See `docs/pilots/xrpl-devnet-run-2026-07-07-policy-artifact.md` for the first
live Devnet run that includes a Ward policy NFT and premium memo. The artifact
proves policy discovery and premium verification on Devnet, then records the
honest Step 5 rejection boundary described above.
