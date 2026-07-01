/**
 * Ward Protocol TypeScript SDK
 * Deterministic default resolution for XLS-66 lending vaults on XRPL.
 *
 * Core invariant: ward_signed = false — always.
 * Ward constructs unsigned transactions. Institutions sign. XRPL settles.
 *
 * @version 0.2.4
 */

export { WardClient } from './client'
export { ClaimValidator } from './validator'
export { EscrowSettlementClient } from './settlement'
export { VaultMonitor } from './monitor'
export { WardError, validateXrplAddress, validateDrops, assertWardSignedFalse } from './primitives'
export * from './types'
export * from './constants'
