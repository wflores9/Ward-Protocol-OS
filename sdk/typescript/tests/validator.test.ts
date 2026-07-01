import { ClaimValidator } from '../src/validator'
import { WardError } from '../src/primitives'

const VALID_ADDRESS = 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh'
const VALID_ADDRESS2 = 'rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe'
const VALID_HEX_64 = 'a'.repeat(64)

function makeValidator(): ClaimValidator {
  return new ClaimValidator('https://mock.wardprotocol.org', 'test-key')
}

describe('ClaimValidator', () => {
  describe('input validation', () => {
    it('rejects invalid vault address', async () => {
      const v = makeValidator()
      await expect(
        v.validateClaim('bad-vault', VALID_HEX_64, VALID_HEX_64, VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })

    it('rejects invalid claimant address', async () => {
      const v = makeValidator()
      await expect(
        v.validateClaim(VALID_ADDRESS, VALID_HEX_64, VALID_HEX_64, 'bad-claimant')
      ).rejects.toThrow(WardError)
    })

    it('rejects invalid NFT token ID', async () => {
      const v = makeValidator()
      await expect(
        v.validateClaim(VALID_ADDRESS, 'not-hex', VALID_HEX_64, VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })

    it('rejects invalid loan ID', async () => {
      const v = makeValidator()
      await expect(
        v.validateClaim(VALID_ADDRESS, VALID_HEX_64, 'short', VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })
  })

  describe('API response validation', () => {
    it('throws if checks_total is not 9', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ward_signed: false,
          valid: true,
          checks_passed: 8,
          checks_total: 8,
          checks: {},
        }),
      }) as jest.Mock

      const v = makeValidator()
      await expect(
        v.validateClaim(VALID_ADDRESS, VALID_HEX_64, VALID_HEX_64, VALID_ADDRESS2)
      ).rejects.toThrow(WardError)
    })

    it('returns result when all checks pass', async () => {
      const mockResult = {
        ward_signed: false,
        valid: true,
        checks_passed: 9,
        checks_total: 9,
        checks: {
          vault_exists: true, nft_valid: true, not_expired: true,
          address_match: true, default_confirmed: true, no_escrow_pending: true,
          kyc_valid: true, domain_valid: true, no_duplicate: true,
        },
      }
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      }) as jest.Mock

      const v = makeValidator()
      const result = await v.validateClaim(VALID_ADDRESS, VALID_HEX_64, VALID_HEX_64, VALID_ADDRESS2)
      expect(result.valid).toBe(true)
      expect(result.checks_total).toBe(9)
      expect(result.ward_signed).toBe(false)
    })
  })
})
