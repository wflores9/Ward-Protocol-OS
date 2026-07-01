"""
Ward Protocol SDK — Public Package API  v0.2.10

    from ward import WardClient, VaultMonitor, ClaimValidator
    from ward import EscrowSettlement, PoolHealthMonitor
    from ward import ValidationError, LedgerError, LicenseTier
    from ward import PoolHealth, VerifiedDefault, ValidationResult

Changelog:
    v0.2.10  Pre-mainnet audit: dep freshness, SSRF, XSS, GHA SHA pins, hygiene.
    v0.2.5  SSRF RPC allowlist; ward_signed structural invariant test.
    v0.2.4  README/stats corrected; CI workflows overhauled; ruff.toml added.
    v0.2.3  On-chain coverage registry; webhook notifications; TypeScript SDK.
    v0.2.2  Add ripple_time_now, get_ledger_close_time exports; full __all__.
    v0.2.1  Add ClaimValidator, ValidationResult, EscrowSettlement, EscrowRecord.
    v0.2.0  Initial modular split from ward_client monolith.
"""

__version__ = "0.2.10"


from ward.client import WardClient
from ward.constants import (
    ALLOWED_WS_URLS,
    CLAIM_RATE_LIMIT_MAX,
    CLAIM_RATE_LIMIT_WINDOW_S,
    CREDENTIAL_NFT_TAXON,
    DEFAULT_MAINNET_URL,
    DEFAULT_MAINNET_WS,
    DEFAULT_TESTNET_URL,
    DEFAULT_TESTNET_WS,
    ESCROW_CANCEL_HOURS,
    ESCROW_DISPUTE_HOURS,
    LSF_LOAN_DEFAULT,
    MIN_COVERAGE_RATIO,
    MONITOR_HEARTBEAT_TIMEOUT_S,
    RIPPLE_EPOCH_OFFSET,
    TF_BURNABLE,
    TF_TRANSFERABLE,
    VALID_KYC_TYPES,
    WARD_CREDENTIAL_TAXON,
    WARD_POLICY_TAXON,
    XRP_MAX_DROPS,
    XRPL_BASE_RESERVE_DROPS,
    XRPL_OWNER_RESERVE_DROPS,
    LicenseTier,
    VaultRegistration,
)
from ward.pool import PoolHealth, PoolHealthMonitor
from ward.primitives import (
    ConfigurationError,
    LedgerError,
    SecurityError,
    ValidationError,
    WardError,
    build_unsigned_tx,
    check_rate_limit,
    generate_claim_preimage,
    get_ledger_close_time,
    make_preimage_condition,
    ripple_time_now,
    validate_condition_hex,
    validate_drops,
    validate_drops_amount,
    validate_nft_id,
    validate_xrpl_address,
)
from ward.registry import (
    deregister_vault,
    get_vault,
    get_vaults,
    register_vault,
)
from ward.settlement import EscrowRecord, EscrowSettlement
from ward.validator import ClaimValidator, ValidationResult
from ward.vault_monitor import DefaultSignal, VaultMonitor, VerifiedDefault

__all__ = [
    # Registry
    "register_vault",
    "get_vaults",
    "get_vault",
    "deregister_vault",
    "VaultRegistration",
    # Core SDK classes
    "WardClient",
    "VaultMonitor",
    "VerifiedDefault",
    "DefaultSignal",
    "ClaimValidator",
    "ValidationResult",
    "EscrowSettlement",
    "EscrowRecord",
    "PoolHealthMonitor",
    "PoolHealth",
    # Errors
    "WardError",
    "ConfigurationError",
    "ValidationError",
    "SecurityError",
    "LedgerError",
    # Validators / crypto utilities
    "validate_condition_hex",
    "validate_xrpl_address",
    "validate_drops_amount",
    "validate_drops",
    "validate_nft_id",
    "check_rate_limit",
    "make_preimage_condition",
    "generate_claim_preimage",
    "get_ledger_close_time",
    "ripple_time_now",
    "build_unsigned_tx",
    # Licensing tier
    "LicenseTier",
    # Network endpoints
    "DEFAULT_TESTNET_URL",
    "DEFAULT_TESTNET_WS",
    "DEFAULT_MAINNET_URL",
    "DEFAULT_MAINNET_WS",
    "ALLOWED_WS_URLS",
    # NFT / taxon constants
    "WARD_POLICY_TAXON",
    "WARD_CREDENTIAL_TAXON",
    "CREDENTIAL_NFT_TAXON",
    "TF_BURNABLE",
    "TF_TRANSFERABLE",
    "VALID_KYC_TYPES",
    # Risk / rate constants
    "MIN_COVERAGE_RATIO",
    "CLAIM_RATE_LIMIT_MAX",
    "CLAIM_RATE_LIMIT_WINDOW_S",
    "ESCROW_DISPUTE_HOURS",
    "ESCROW_CANCEL_HOURS",
    "MONITOR_HEARTBEAT_TIMEOUT_S",
    # XRPL chain constants
    "LSF_LOAN_DEFAULT",
    "XRPL_BASE_RESERVE_DROPS",
    "XRPL_OWNER_RESERVE_DROPS",
    "XRP_MAX_DROPS",
    "RIPPLE_EPOCH_OFFSET",
]
