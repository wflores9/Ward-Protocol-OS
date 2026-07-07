# XRPL Devnet Run — Ward Policy Artifact + Canonical Evidence

Date: 2026-07-07

This run extends the prior XLS-65/66 Devnet lifecycle by minting a real Ward
policy NFT, paying a Ward premium memo to a Devnet pool wallet, and feeding the
result into `scripts/run_xrpl_devnet_evidence.py` without manual policy flags.

The result is not an approval. It is the first canonical Ward evidence bundle
where Steps 1-4 pass against live Devnet state and the validator rejects at Step
5 because the post-`LoanManage` loan object no longer exposes a positive
outstanding loss.

## Network

- Network: XRPL Devnet
- WebSocket: `wss://s.devnet.rippletest.net:51233`
- JSON-RPC: `https://s.devnet.rippletest.net:51234`
- rippled/xrpld build: `3.2.0`
- Source tag: `2606260002`

## Ward Policy Artifact

```json
{
  "policy_nft_id": "00010000AA9977CFE4B3E2D604C7E12F19EDD321D5BC804AD8FE48E30034B15F",
  "pool_address": "rwt3MqmgroDvoF2bpwRL2VTe11uFPjHntd",
  "claimant_address": "rGZs5kq681A8kVG1F3SuKQcTfJPv4ZVFuC",
  "defaulted_vault": "rpM7yMRtSyTzckN7cwSDyGSAitZq8Zez7G",
  "coverage_drops": 2000000,
  "expiry_ledger_time": 999999999,
  "nft_taxon": 281,
  "ward_signed": false
}
```

## Transactions

| Step | Result | Hash |
| --- | --- | --- |
| VaultCreate | `tesSUCCESS` | `9DFF1A84627EF46711C3A3411EF8C7C70E6C7783535EECDA9819C811E13D960C` |
| VaultDeposit | `tesSUCCESS` | `838714112F9BC562222A5FF3AFBFA7F51697F84A21D7B2F68AF4B6591F4807F5` |
| WardPolicyNFTokenMint | `tesSUCCESS` | `2B116C11C1E81C8B94EF6977F0DC9D3D50E5B681C933769170FF82D115799D87` |
| WardPolicyPremiumPayment | `tesSUCCESS` | `50339F66F0A6F8910C3CEC3464B31B1F02DED446F9752CEBD0420EA339DE0C43` |
| LoanBrokerSet | `tesSUCCESS` | `CA8370D21783F15570E3742A628ED34FC9CB827728D8EB65054B22CFAFECC691` |
| LoanBrokerCoverDeposit | `tesSUCCESS` | `D037846D683B6950B59772C684110F832BA462728AC6FB3C0558D7C78C7E29DF` |
| LoanSet | `tesSUCCESS` | `E95CEC0064963CC8F9230E8A7153A7DCABFBDC84A6A7BB4F2B7BCA323965BD85` |
| LoanManageRetryAfterGrace | `tesSUCCESS` | `B974B6E23E9D2F89392DA929501F27E504F9CF73E743F8FB1FB9D4D3DC664882` |

The first `LoanManage` attempt returned `tecTOO_SOON`; the script waited 150
seconds and retried after the payment interval plus grace window.

## Ward Evidence Result

```json
{
  "ward_signed": false,
  "approved": false,
  "steps_passed": 4,
  "rejection_reason": "Vault loss not positive: 0"
}
```

Passed checks:

- Step 1: Policy NFT located
- Step 2: Coverage and premium confirmed
- Step 3: Vault binding verified
- Step 4: Default signal verified

Failed check:

- Step 5: Loss math bounded

## Finding

The policy artifact and premium path are valid. The evidence runner can consume
the lifecycle artifact without manual policy flags. Ward correctly refuses to
approve settlement because the validation point is too late: after
`LoanManageRetryAfterGrace`, the loan object no longer contains a positive loss
for Ward to bound.

The next Devnet run must capture Ward validation at the pre-default resolution
point, before the `LoanManage` transition clears or settles the outstanding
loss fields. This is an implementation sequencing issue, not a signer-boundary
issue. `ward_signed = False` remained intact.
