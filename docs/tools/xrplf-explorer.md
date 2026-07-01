# XRPLF Technical Explorer — Ward Protocol Reference

Explorer: https://explorer.xrplf.org
Built by Wietse Wind, XRPLF. Covers XRPL mainnet, testnet, and Xahau.

## Ward Nine-Check Verification Map

### Check 1 — Policy NFT (taxon 281)
Look up vault address → AccountNFTs → filter by taxon 281.
Verify raw NFT metadata, flags, URI.

### Check 2 — Policy Not Expired
Pull ledger close_time from any recent ledger.
Compare against expiry value in NFT metadata URI.

### Check 3 — Vault Address Match
Cross-reference NFT metadata URI against vault account directly.

### Check 4 — Default Flag (LSF_LOAN_DEFAULT)
Pull vault account object → AccountRoot flags field.
Verify LSF_LOAN_DEFAULT bit is set in raw bitmask.

### Check 5 — Vault Loss > Zero
Check vault account balance and escrow objects for net loss state.

### Check 6 — Pool Coverage Available
Pull pool account balance directly. Confirm usable balance >= payout.

### Check 7 — NFT Still Live
Search NFT by ID. If burned, it will not appear in AccountNFTs.

### Check 8 — Claimant Holds NFT
Pull claimant address → AccountNFTs → confirm NFT ID present.

### Check 9 — Pool Solvent, Rate Limit Clear
Pool account balance + recent transaction history.
Verify claim frequency <= 3 claims per NFT per 300 seconds.

## Additional Ward Use Cases

- **Altnet verification** — confirm F·01–F·04 transaction hashes landed on-chain
- **Escrow state** — inspect PREIMAGE-SHA-256 escrow objects for F·03/F·04
- **Xahau** — hooks testing if Ward extends to Xahau network
- **Raw transaction inspection** — debug resolution flow against live ledger state

## Developer Notes

Use explorer.xrplf.org as the primary manual verification tool during:
- Altnet E2E test runs
- Ward-Conformant client onboarding verification
- Pre-mainnet audit preparation
