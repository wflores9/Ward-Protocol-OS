/**
 * Ward Protocol TypeScript SDK — Type Definitions
 * ward_signed = false — always
 */

export interface UnsignedTransaction {
  tx_dict: Record<string, unknown>
  ward_signed: false  // type literal — cannot be true
}

export interface VaultRegistration {
  vault_id: string
  vault_address: string
  status: 'registered' | 'active' | 'defaulted'
  ledger_index: number
  ward_signed: false
}

export interface PolicyNFT {
  policy_id: string
  nft_token_id: string
  vault_address: string
  depositor_address: string
  coverage_drops: number
  expiry: number  // XRPL ledger time
  taxon: 281      // type literal
  ward_signed: false
}

export interface ClaimValidationResult {
  valid: boolean
  checks_passed: number
  checks_total: 9   // type literal
  checks: {
    vault_exists: boolean
    nft_valid: boolean
    not_expired: boolean
    address_match: boolean
    default_confirmed: boolean
    no_escrow_pending: boolean
    kyc_valid: boolean
    domain_valid: boolean
    no_duplicate: boolean
  }
  rejection_step?: number
  rejection_reason?: string
  ward_signed: false
}

export interface EscrowSettlement {
  unsigned_tx: UnsignedTransaction
  condition_hex: string
  claim_id: string
  dispute_deadline: number  // XRPL ledger time
  institution_signs: true   // type literal
  ward_signed: false
}

export interface VaultHealth {
  vault_address: string
  health_ratio: number
  status: 'healthy' | 'warning' | 'elevated' | 'critical' | 'defaulted'
  ledger_index: number
  ward_signed: false
}

export type WardNetwork = 'altnet' | 'mainnet' | 'testnet'

export interface WardConfig {
  network: WardNetwork
  api_url?: string          // defaults to api.wardprotocol.org
  institution_key: string   // X-Institution-Key
  timeout_ms?: number       // default 30000
}

export type WebhookEvent =
  | 'vault.health.warning'
  | 'vault.health.elevated'
  | 'vault.health.critical'
  | 'vault.default.detected'
  | 'vault.default.resolved'
  | 'vault.claim.filed'
  | 'vault.claim.settled'

export interface WebhookPayload {
  event: WebhookEvent
  vault_address: string
  health_ratio: number | null
  ledger_index: number
  timestamp: number
  ward_signed: false
}
