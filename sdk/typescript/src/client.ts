import { WardConfig, VaultRegistration, PolicyNFT, UnsignedTransaction } from './types'
import { WardError, validateXrplAddress, validateDrops, assertWardSignedFalse } from './primitives'
import { WARD_API_URL } from './constants'

type ApiResponse = Record<string, unknown> & { ward_signed: boolean }

export class WardClient {
  private readonly baseUrl: string
  private readonly headers: Record<string, string>

  constructor(private readonly config: WardConfig) {
    this.baseUrl = config.api_url ?? WARD_API_URL
    this.headers = {
      'Content-Type': 'application/json',
      'X-Institution-Key': config.institution_key,
    }
  }

  /** F·01 — Register an XLS-66 vault */
  async registerVault(vaultAddress: string): Promise<VaultRegistration> {
    validateXrplAddress(vaultAddress)
    const res = await this._post('/vaults/register', { vault_address: vaultAddress })
    assertWardSignedFalse(res)
    return res as unknown as VaultRegistration
  }

  /** F·02 — Issue a KYC credential (XLS-70, taxon 282) */
  async issueCredential(depositorAddress: string): Promise<UnsignedTransaction> {
    validateXrplAddress(depositorAddress)
    const res = await this._post('/credentials/issue', { depositor_address: depositorAddress })
    assertWardSignedFalse(res)
    return res as unknown as UnsignedTransaction
  }

  /** F·03 — Purchase a policy NFT (taxon 281) */
  async purchaseCoverage(
    vaultAddress: string,
    depositorAddress: string,
    coverageDrops: number,
    expiryLedgerTime: number,
  ): Promise<PolicyNFT> {
    validateXrplAddress(vaultAddress)
    validateXrplAddress(depositorAddress)
    validateDrops(coverageDrops)
    const res = await this._post('/purchase', {
      vault_address: vaultAddress,
      depositor_address: depositorAddress,
      coverage_drops: coverageDrops,
      expiry: expiryLedgerTime,
    })
    assertWardSignedFalse(res)
    return res as unknown as PolicyNFT
  }

  /** F·05 — Validate a default claim (9 on-ledger checks) */
  async validateClaim(
    claimantAddress: string,
    nftTokenId: string,
    defaultedVault: string,
    loanId: string,
    poolAddress: string,
  ): Promise<Record<string, unknown>> {
    validateXrplAddress(claimantAddress)
    validateXrplAddress(defaultedVault)
    validateXrplAddress(poolAddress)
    const res = await this._post('/validate', {
      claimant_address: claimantAddress,
      policy_nft_id: nftTokenId,
      vault_id: defaultedVault,
      loan_id: loanId,
      pool_address: poolAddress,
    })
    assertWardSignedFalse(res)
    return res
  }

  /** F·06 — Create a claim escrow (unsigned EscrowCreate) */
  async createClaimEscrow(
    poolAddress: string,
    claimantAddress: string,
    payoutDrops: number,
    conditionHex: string,
    nftTokenId: string,
    claimId: string,
  ): Promise<UnsignedTransaction> {
    validateXrplAddress(poolAddress)
    validateXrplAddress(claimantAddress)
    validateDrops(payoutDrops)
    const res = await this._post('/settlement/escrow', {
      pool_address: poolAddress,
      claimant_address: claimantAddress,
      payout_drops: payoutDrops,
      condition_hex: conditionHex,
      nft_token_id: nftTokenId,
      claim_id: claimId,
    })
    assertWardSignedFalse(res)
    return res as unknown as UnsignedTransaction
  }

  /** List all vaults registered under this institution key */
  async listVaults(): Promise<VaultRegistration[]> {
    const res = await this._get('/vaults')
    assertWardSignedFalse(res)
    return res['vaults'] as VaultRegistration[]
  }

  /** Get health ratio for a vault */
  async getVaultHealth(vaultAddress: string): Promise<Record<string, unknown>> {
    validateXrplAddress(vaultAddress)
    const res = await this._get(`/dashboard/vault/${vaultAddress}/health`)
    assertWardSignedFalse(res)
    return res
  }

  private async _post(path: string, body: unknown): Promise<ApiResponse> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new WardError(`Ward API error ${res.status}: ${JSON.stringify(err)}`)
    }
    return res.json() as Promise<ApiResponse>
  }

  private async _get(path: string): Promise<ApiResponse> {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this.headers })
    if (!res.ok) {
      throw new WardError(`Ward API error ${res.status}`)
    }
    return res.json() as Promise<ApiResponse>
  }
}
