export const WARD_POLICY_TAXON = 281 as const
export const WARD_KYC_TAXON = 282 as const
export const HEALTH_RATIO_THRESHOLD = 1.5 as const
export const DEFAULT_CONFIRMATION_CLOSES = 3 as const
export const DISPUTE_WINDOW_SECONDS = 48 * 60 * 60  // 48 hours

export const NETWORK_CONFIG = {
  altnet: {
    rpc: 'https://s.altnet.rippletest.net:51234',
    ws: 'wss://s.altnet.rippletest.net:51233',
    faucet: 'https://faucet.altnet.rippletest.net/accounts',
  },
  mainnet: {
    rpc: 'https://xrplcluster.com',
    ws: 'wss://xrplcluster.com',
    faucet: null,
  },
} as const

export const WARD_API_URL = 'https://api.wardprotocol.org'
