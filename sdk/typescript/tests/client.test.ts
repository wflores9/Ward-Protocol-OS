import { WardClient } from '../src/client'
import { WardError } from '../src/primitives'

const VALID_ADDRESS = 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh'
const VALID_ADDRESS2 = 'rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe'

function makeClient(overrides: Record<string, unknown> = {}): WardClient {
  return new WardClient({
    network: 'altnet',
    institution_key: 'test-key',
    api_url: 'https://mock.wardprotocol.org',
    ...overrides,
  })
}

describe('WardClient', () => {
  describe('input validation', () => {
    it('rejects invalid vault address in registerVault', async () => {
      const client = makeClient()
      await expect(client.registerVault('not-valid')).rejects.toThrow(WardError)
    })

    it('rejects invalid depositor address in issueCredential', async () => {
      const client = makeClient()
      await expect(client.issueCredential('bad-addr')).rejects.toThrow(WardError)
    })

    it('rejects invalid vault in purchaseCoverage', async () => {
      const client = makeClient()
      await expect(
        client.purchaseCoverage('bad-vault', VALID_ADDRESS2, 1_000_000, 9999999)
      ).rejects.toThrow(WardError)
    })

    it('rejects fractional drops in purchaseCoverage', async () => {
      const client = makeClient()
      await expect(
        client.purchaseCoverage(VALID_ADDRESS, VALID_ADDRESS2, 1.5, 9999999)
      ).rejects.toThrow(WardError)
    })

    it('rejects negative drops in purchaseCoverage', async () => {
      const client = makeClient()
      await expect(
        client.purchaseCoverage(VALID_ADDRESS, VALID_ADDRESS2, -100, 9999999)
      ).rejects.toThrow(WardError)
    })

    it('rejects invalid address in getVaultHealth', async () => {
      const client = makeClient()
      await expect(client.getVaultHealth('not-r')).rejects.toThrow(WardError)
    })
  })

  describe('assertWardSignedFalse integration', () => {
    it('throws if API returns ward_signed: true', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ward_signed: true, vaults: [] }),
      }) as jest.Mock

      const client = makeClient()
      await expect(client.listVaults()).rejects.toThrow(WardError)
    })

    it('passes when API returns ward_signed: false', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ward_signed: false, vaults: [] }),
      }) as jest.Mock

      const client = makeClient()
      const vaults = await client.listVaults()
      expect(vaults).toEqual([])
    })
  })

  describe('validateClaim', () => {
    it('rejects invalid claimant address', async () => {
      const client = makeClient()
      await expect(
        client.validateClaim('bad-addr', 'A'.repeat(64), VALID_ADDRESS, 'B'.repeat(64), VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })
    it('rejects invalid defaulted vault address', async () => {
      const client = makeClient()
      await expect(
        client.validateClaim(VALID_ADDRESS, 'A'.repeat(64), 'bad-vault', 'B'.repeat(64), VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })
    it('rejects invalid pool address', async () => {
      const client = makeClient()
      await expect(
        client.validateClaim(VALID_ADDRESS, 'A'.repeat(64), VALID_ADDRESS2, 'B'.repeat(64), 'bad-pool')
      ).rejects.toThrow(WardError)
    })
    it('passes ward_signed=false check on approval', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ward_signed: false, approved: true, checks_passed: 9 }),
      }) as jest.Mock
      const client = makeClient()
      const result = await client.validateClaim(
        VALID_ADDRESS, 'A'.repeat(64), VALID_ADDRESS2, 'B'.repeat(64), VALID_ADDRESS
      )
      expect(result.ward_signed).toBe(false)
      expect(result.approved).toBe(true)
    })
  })

  describe('createClaimEscrow', () => {
    it('rejects invalid pool address', async () => {
      const client = makeClient()
      await expect(
        client.createClaimEscrow('bad-pool', VALID_ADDRESS, 1_000_000, 'A'.repeat(78), 'B'.repeat(64), 'claim-1')
      ).rejects.toThrow(WardError)
    })
    it('rejects invalid claimant address', async () => {
      const client = makeClient()
      await expect(
        client.createClaimEscrow(VALID_ADDRESS, 'bad-addr', 1_000_000, 'A'.repeat(78), 'B'.repeat(64), 'claim-1')
      ).rejects.toThrow(WardError)
    })
    it('rejects fractional drops', async () => {
      const client = makeClient()
      await expect(
        client.createClaimEscrow(VALID_ADDRESS, VALID_ADDRESS2, 1.5, 'A'.repeat(78), 'B'.repeat(64), 'claim-1')
      ).rejects.toThrow(WardError)
    })
    it('passes ward_signed=false on success', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ward_signed: false, tx_dict: {}, escrow_sequence: 1 }),
      }) as jest.Mock
      const client = makeClient()
      const result = await client.createClaimEscrow(
        VALID_ADDRESS, VALID_ADDRESS2, 1_000_000, 'A'.repeat(78), 'B'.repeat(64), 'claim-1'
      )
      expect(result.ward_signed).toBe(false)
    })
  })
})
