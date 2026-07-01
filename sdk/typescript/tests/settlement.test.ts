import { EscrowSettlementClient } from '../src/settlement'
import { WardError } from '../src/primitives'

const VALID_ADDRESS = 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh'
const VALID_ADDRESS2 = 'rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe'
const VALID_HEX_64 = 'b'.repeat(64)
const VALID_CONDITION = 'A0258020' + 'c'.repeat(64) + '810120'

function makeClient(): EscrowSettlementClient {
  return new EscrowSettlementClient('https://mock.wardprotocol.org', 'test-key')
}

describe('EscrowSettlementClient', () => {
  describe('input validation', () => {
    it('rejects invalid vault address', async () => {
      const c = makeClient()
      await expect(c.createEscrow('bad', VALID_HEX_64, VALID_ADDRESS2, VALID_CONDITION)).rejects.toThrow(WardError)
    })

    it('rejects invalid claimant address', async () => {
      const c = makeClient()
      await expect(c.createEscrow(VALID_ADDRESS, VALID_HEX_64, 'bad', VALID_CONDITION)).rejects.toThrow(WardError)
    })

    it('rejects invalid NFT token ID', async () => {
      const c = makeClient()
      await expect(c.createEscrow(VALID_ADDRESS, 'not-valid-hex', VALID_ADDRESS2, VALID_CONDITION)).rejects.toThrow(WardError)
    })

    it('rejects non-hex condition_hex', async () => {
      const c = makeClient()
      await expect(c.createEscrow(VALID_ADDRESS, VALID_HEX_64, VALID_ADDRESS2, 'ZZZZ')).rejects.toThrow(WardError)
    })

    it('rejects empty condition_hex', async () => {
      const c = makeClient()
      await expect(c.createEscrow(VALID_ADDRESS, VALID_HEX_64, VALID_ADDRESS2, '')).rejects.toThrow(WardError)
    })
  })

  describe('API response validation', () => {
    it('throws if institution_signs is not true', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ward_signed: false,
          institution_signs: false,
          unsigned_tx: { tx_dict: {}, ward_signed: false },
          condition_hex: VALID_CONDITION,
          claim_id: VALID_HEX_64,
          dispute_deadline: 99999,
        }),
      }) as jest.Mock

      const c = makeClient()
      await expect(c.createEscrow(VALID_ADDRESS, VALID_HEX_64, VALID_ADDRESS2, VALID_CONDITION)).rejects.toThrow(WardError)
    })

    it('ward_signed is always false in response', async () => {
      const mockResult = {
        ward_signed: false,
        institution_signs: true,
        unsigned_tx: { tx_dict: { TransactionType: 'EscrowCreate' }, ward_signed: false },
        condition_hex: VALID_CONDITION,
        claim_id: VALID_HEX_64,
        dispute_deadline: 800000000,
      }
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      }) as jest.Mock

      const c = makeClient()
      const result = await c.createEscrow(VALID_ADDRESS, VALID_HEX_64, VALID_ADDRESS2, VALID_CONDITION)
      expect(result.ward_signed).toBe(false)
      expect(result.institution_signs).toBe(true)
    })
  })
})
