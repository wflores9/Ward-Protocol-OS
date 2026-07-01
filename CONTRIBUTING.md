# Contributing to Ward Protocol

Ward is a **software specification** for deterministic default resolution on XLS-66 XRPL lending vaults.

Core rule: Ward **never** signs or submits transactions. Every mutation returns an unsigned transaction prepared for institutional signing.

## Architectural Layers

- **`ward/`** — Protocol SDK (15 modules, 559 Python · 22 Rust · 53 TypeScript tests)
  - `WardClient`: Purchases default-protection coverage (unsigned NFTokenMint + Payment)
  - `ClaimValidator`: 9-step on-chain claim validation — all state from XRPL
  - `EscrowSettlement`: PREIMAGE-SHA-256 conditioned escrow lifecycle
  - `PoolHealthMonitor`: Coverage pool solvency and dynamic premium monitoring
  - `VaultMonitor`: WebSocket default detection with 3-ledger confirmation
  - **Invariant**: No signing, no submission, no wallet keys stored

- **`sdk/typescript/`** — TypeScript SDK (53/53 tests)
  - Full type-safe client with strict `ward_signed: false` type literal
  - All 6 Ward Protocol flows implemented

- **`ward_client.py`** — Deprecated shim (re-exports from `ward.*` only)

## Contribution Guidelines

- Protocol / spec changes → modify `ward/` and sync to XRPLF Discussion #474
- SDK, demo, test, or documentation improvements → target `ward/`, `sdk/`, `tests/`
- `ward/` must remain signing-free at all times
- Always run `pytest` before pushing (keep 634/634 green)
- Run `ruff check ward/ --select=E,F,W,I --ignore=E501` and `ruff format ward/ --check`
- Use conventional commits (fix:, feat:, docs:, refactor:, etc.)

## Related

- XRPLF Discussion #474: github.com/XRPLF/XRPL-Standards/discussions/474
- On-chain proof: `testnet_proof.md`

Questions? Open an issue or reach out at wflores@wardprotocol.org
