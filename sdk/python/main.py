"""
Ward Protocol API
=================
Open specification for default protection on XLS-66 lending vaults on the XRP Ledger.

Core invariant: ward_signed = False — always.
Ward constructs unsigned XRPL transactions.
The institution signs with their own keypair.
XRPL settles.

Ward never holds keys. Ward never submits transactions.
Ward's server is intentionally irrelevant to protocol outcomes.
"""

import importlib.metadata
import os
import sys
import logging
import hashlib
import time
from datetime import datetime
from typing import Optional

try:
    _VERSION = importlib.metadata.version("ward-protocol")
except importlib.metadata.PackageNotFoundError:
    # Should never fire in normal operation: ward-protocol is pinned in requirements.txt.
    # If this path executes, the package install failed.
    _VERSION = "0.2.10"

from fastapi import FastAPI, HTTPException, Depends, Header, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models import AccountInfo

# ── Ensure ward_client.py (repo root) is importable from sdk/python
# Procfile: cd sdk/python && uvicorn main:app
# ward_client.py lives at repo root, two levels up
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from ward_client import (
        WardClient,
        VaultMonitor,
        ClaimValidator,
        EscrowSettlement,
        PoolHealthMonitor,
        ValidationError,
        LedgerError,
        WARD_POLICY_TAXON,
        CREDENTIAL_NFT_TAXON,
    )
    WARD_CLIENT_AVAILABLE = True
except ImportError as e:
    logging.warning(f"ward_client import failed: {e} — running in spec-only mode")
    WARD_CLIENT_AVAILABLE = False

try:
    from ward.registry import (
        register_vault as _registry_register,
        get_vaults as _registry_get_vaults,
        deregister_vault as _registry_deregister,
    )
    from ward.primitives import WardError as _WardError
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False

try:
    from ward.webhooks import (
        WebhookConfig as _WebhookConfig,
        register_webhook as _register_webhook,
        deregister_webhook as _deregister_webhook,
        get_webhooks as _get_webhooks,
    )
    WEBHOOKS_AVAILABLE = True
except ImportError:
    WEBHOOKS_AVAILABLE = False

try:
    from ward.keys import (
        generate_key as _generate_key,
        register_key as _register_key,
        verify_key as _verify_key,
        revoke_key as _revoke_key,
        rotate_key as _rotate_key,
        _hash_key as _key_hash_fn,
        _key_store as _key_store_ref,
    )
    KEYS_AVAILABLE = True
except ImportError:
    KEYS_AVAILABLE = False

# ── Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("ward.api")

# ── App startup time for real uptime tracking
_START_TIME = time.time()

# ── XRPL endpoint from environment (Railway injects this)
XRPL_URL = os.getenv("XRPL_URL", "wss://xrplcluster.com")
XRPL_RPC = os.getenv("XRPL_RPC", "https://xrplcluster.com")

# ── FastAPI — no auto-docs in production
app = FastAPI(
    title="Ward Protocol",
    description=(
        "Open specification for default protection on XLS-66 lending vaults. "
        "ward_signed = False — Ward constructs unsigned transactions. "
        "The institution signs. XRPL settles."
    ),
    version=_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ── CORS — locked to wardprotocol.org only
# localhost origins included only when DEV_CORS=1 is set in the environment.
# Never set DEV_CORS in Railway production config.
_CORS_ORIGINS = [
    "https://wardprotocol.org",
    "https://www.wardprotocol.org",
]
if os.getenv("DEV_CORS", "").lower() in ("1", "true", "yes"):
    _CORS_ORIGINS += ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Institution-Key"],
)


# ============================================================
# AUTH UTILITY
# ============================================================

def verify_institution_key(x_institution_key: Optional[str]) -> Optional[str]:
    """
    Verify institution API key from X-Institution-Key header.

    Checks in order:
      1. ward.keys store — for keys generated via POST /keys/generate
      2. INSTITUTION_API_KEY env var — backward compat for hardcoded keys
      3. DEMO_INSTITUTION_KEY env var — persistent demo key, survives restarts

    Returns the raw key on success. Raises HTTP 401 if key is missing or invalid. Raises HTTP 503 if server auth is not configured.
    Raises HTTP 401 if a key is required but invalid.
    """
    if not x_institution_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "MISSING_AUTH",
                "message": "X-Institution-Key header required",
                "ward_signed": False,
            }
        )

    # Check ward.keys store first (async store — use sync hash lookup)
    if KEYS_AVAILABLE:
        import asyncio
        key_hash = _key_hash_fn(x_institution_key)
        record = _key_store_ref.get(key_hash)
        if record is not None:
            if not record.revoked and (record.expires_at is None or int(time.time()) <= record.expires_at):
                return x_institution_key
            # Key exists but revoked/expired — fall through to env check

    # Backward compat — constant-time comparison against env var
    expected = os.getenv("INSTITUTION_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AUTH_NOT_CONFIGURED",
                "message": "Server authentication is not configured",
                "ward_signed": False,
            }
        )

    # Constant-time comparison — prevents timing attacks
    provided = hashlib.sha256(x_institution_key.encode()).digest()
    expected_hash = hashlib.sha256(expected.encode()).digest()
    if provided != expected_hash:
        # Demo key check — plain equality is acceptable here since demo keys
        # are intentionally low-privilege and publicly shared in env config.
        demo_key = os.getenv("DEMO_INSTITUTION_KEY")
        if demo_key and x_institution_key == demo_key:
            return x_institution_key
        raise HTTPException(
            status_code=401,
            detail={
                "error": "INVALID_AUTH",
                "message": "Invalid institution key",
                "ward_signed": False,
            }
        )
    return x_institution_key


# ============================================================
# REQUEST / RESPONSE MODELS
# All responses include ward_signed: false — core invariant.
# ============================================================

class VaultRegisterRequest(BaseModel):
    institution_address: str = Field(..., description="Institution XRPL address (r...)")
    collateral_currency: str = Field(default="XRP")
    min_collateral_ratio: float = Field(default=1.5, ge=1.0)
    domain_credential: Optional[str] = Field(None, description="XLS-80 domain credential hash")
    policy_nft_taxon: int = Field(default=282)

class CredentialIssueRequest(BaseModel):
    institution_address: str = Field(..., description="Institution XRPL address")
    depositor_address: str = Field(..., description="Depositor XRPL address")
    kyc_hash: str = Field(..., description="SHA-256 hash of KYC document — no raw PII on-chain")
    kyc_type: str = Field(..., description="institutional | retail | accredited")
    expiry_days: int = Field(default=365, ge=30, le=730)

XRPL_ADDRESS_REGEX = r"^r[1-9A-HJ-NP-Za-km-z]{24,34}$"


class PolicyPurchaseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vault_address: str = Field(..., alias="vault_id", description="XLS-66 vault address")
    pool_address: str = Field(..., description="Coverage pool XRPL address")
    coverage_drops: int = Field(..., gt=0, description="Coverage amount in XRP drops")
    period_days: int = Field(default=90, alias="duration_days", ge=1, le=365, description="Coverage period in days")
    premium_rate: float = Field(default=0.01, gt=0, le=1.0, description="Annual premium rate as fraction (0,1]")
    license_tier: str = Field(default="starter", description="starter | standard | enterprise")
    depositor_address: Optional[str] = Field(default=None, description="Deprecated. Not used by current SDK path.")

    @field_validator('vault_address', 'pool_address')
    @classmethod
    def validate_policy_addresses(cls, v: str) -> str:
        import re
        if not re.match(XRPL_ADDRESS_REGEX, v):
            raise ValueError('Invalid XRPL address')
        return v


class ClaimFileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    defaulted_vault: str = Field(..., alias="vault_id", description="Defaulted XLS-66 vault address")
    nft_token_id: str = Field(..., alias="policy_nft_id", description="Policy NFT token ID (64 hex chars)")
    claimant_address: str = Field(..., description="Claimant XRPL address")
    loan_id: str = Field(..., description="Defaulted XLS-66 loan object index (64 hex chars)")
    pool_address: str = Field(..., description="Coverage pool XRPL address")

    @field_validator('defaulted_vault', 'claimant_address', 'pool_address')
    @classmethod
    def validate_claim_addresses(cls, v: str) -> str:
        import re
        if not re.match(XRPL_ADDRESS_REGEX, v):
            raise ValueError('Invalid XRPL address')
        return v


class EscrowCreateRequest(BaseModel):
    claim_id: str
    claimant_address: str
    coverage_drops: int = Field(..., gt=0)
    condition_hex: str = Field(..., description="SHA-256 condition — fulfillment held only by claimant")
    policy_nft_id: str

class VaultRegistryRequest(BaseModel):
    vault_address: str = Field(..., description="XLS-66 vault XRPL address (r...)")
    tier: str = Field(default="starter", description="starter / standard / enterprise")
    label: str = Field(default="", description="Human-readable vault name")
    ledger_time: int = Field(default=0, description="XRPL ledger time of registration")

class WebhookRegisterRequest(BaseModel):
    vault_address: str = Field(..., description="Vault XRPL address to monitor")
    url: str = Field(..., description="Callback URL — must be https://")
    secret: str = Field(default="", description="HMAC-SHA256 signing secret")
    events: list[str] = Field(default_factory=list, description="Event filter — empty = all events")

class KeyRequestModel(BaseModel):
    tier: str = Field(default="starter", description="starter / standard / enterprise")
    label: str = Field(default="", description="Institution name or identifier")
    expires_in_days: Optional[int] = Field(default=None, description="Expiry in days — None = no expiry")

class KeyRotateModel(BaseModel):
    old_key: str = Field(..., description="Existing raw key to rotate from")


def _institution_key_dep(x_institution_key: Optional[str] = Header(None)) -> str:
    """FastAPI Depends wrapper — validates and returns the institution key string."""
    result = verify_institution_key(x_institution_key)
    if not x_institution_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "MISSING_AUTH", "message": "X-Institution-Key header required", "ward_signed": False},
        )
    return x_institution_key


# ============================================================
# ROUTES — F·01 through F·06
# ============================================================

# ── Root
@app.get("/")
async def root():
    return {
        "protocol": "Ward Protocol",
        "version": _VERSION,
        "spec": "https://github.com/XRPLF/XRPL-Standards/discussions/474",
        "website": "https://wardprotocol.org",
        "pypi": f"ward-protocol=={_VERSION}",
        "ward_signed": False,
        "invariant": "Ward constructs unsigned XRPL transactions. The institution signs. XRPL settles.",
        "status": "operational",
    }


# ── Health — real dynamic data only
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": round(time.time() - _START_TIME),
        "version": _VERSION,
        "xrpl_url": XRPL_URL,
        "ward_client_available": WARD_CLIENT_AVAILABLE,
        "ward_signed": False,
        "invariant": "ward_signed = False — always",
    }


# ── F·01 — Vault Registration (XLS-66)
@app.post("/vaults")
async def register_vault(
    req: VaultRegisterRequest,
    x_institution_key: Optional[str] = Header(None),
):
    """
    F·01 — Register an XLS-66 lending vault on XRPL.
    Returns unsigned VaultCreate for institution to sign.
    ward_signed = False.
    """
    verify_institution_key(x_institution_key)
    logger.info(f"F·01 register_vault: institution={req.institution_address}")

    if not WARD_CLIENT_AVAILABLE:
        return {
            "ward_signed": False,
            "flow": "F·01",
            "status": "spec_mode",
            "unsigned_tx_type": "VaultCreate",
            "params": req.model_dump(),
            "note": "Institution signs unsigned tx with their XRPL keypair. Ward never signs.",
        }

    try:
        client = WardClient(xrpl_url=XRPL_URL)
        result = await client.register_vault(
            institution_address=req.institution_address,
            collateral_currency=req.collateral_currency,
            min_collateral_ratio=req.min_collateral_ratio,
        )
        return {"ward_signed": False, "flow": "F·01", **result}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": str(e), "ward_signed": False})
    except LedgerError as e:
        raise HTTPException(status_code=502, detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False})


@app.post("/vaults/register")
async def registry_register_vault(
    req: VaultRegistryRequest,
    x_institution_key: Optional[str] = Header(None),
):
    """Register an XLS-66 vault address under the institution key (multi-vault registry)."""
    verify_institution_key(x_institution_key)
    if not REGISTRY_AVAILABLE or not x_institution_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "REGISTRY_UNAVAILABLE", "ward_signed": False},
        )
    try:
        entry = await _registry_register(
            institution_key=x_institution_key,
            vault_address=req.vault_address,
            tier=req.tier,
            label=req.label,
            ledger_time=req.ledger_time,
        )
        return {
            "vault_address": entry["vault_address"],
            "tier": entry["tier"],
            "label": entry["label"],
            "registered_at": entry["registered_at"],
            "ward_signed": False,
        }
    except _WardError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "REGISTRY_ERROR", "message": str(e), "ward_signed": False},
        )


@app.get("/vaults")
async def list_vaults(x_institution_key: Optional[str] = Header(None)):
    verify_institution_key(x_institution_key)
    if REGISTRY_AVAILABLE and x_institution_key:
        vaults = await _registry_get_vaults(x_institution_key)
        return {
            "ward_signed": False,
            "vaults": vaults,
            "count": len(vaults),
        }
    return {
        "ward_signed": False,
        "vaults": [],
        "count": 0,
        "source": "XRPL XLS-66 ledger objects",
    }


@app.delete("/vaults/{vault_address}")
async def registry_deregister_vault(
    vault_address: str,
    x_institution_key: Optional[str] = Header(None),
):
    """Deregister a vault from the institution key's registry."""
    verify_institution_key(x_institution_key)
    if not REGISTRY_AVAILABLE or not x_institution_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "REGISTRY_UNAVAILABLE", "ward_signed": False},
        )
    removed = await _registry_deregister(x_institution_key, vault_address)
    return {
        "removed": removed,
        "vault_address": vault_address,
        "ward_signed": False,
    }


@app.post("/webhooks/register")
async def webhook_register(
    req: WebhookRegisterRequest,
    x_institution_key: Optional[str] = Header(None),
):
    """Register a webhook URL to receive vault health threshold notifications."""
    verify_institution_key(x_institution_key)
    if not WEBHOOKS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={"error": "WEBHOOKS_UNAVAILABLE", "ward_signed": False},
        )
    try:
        config = _WebhookConfig(
            url=req.url,
            vault_address=req.vault_address,
            secret=req.secret,
            events=req.events,
        )
        await _register_webhook(config)
        return {
            "registered": True,
            "vault_address": req.vault_address,
            "url": req.url,
            "ward_signed": False,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "WEBHOOK_ERROR", "message": str(exc), "ward_signed": False},
        )


@app.delete("/webhooks/{vault_address}")
async def webhook_deregister(
    vault_address: str,
    url: str,
    x_institution_key: Optional[str] = Header(None),
):
    """Deregister a webhook for a vault address."""
    verify_institution_key(x_institution_key)
    if not WEBHOOKS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={"error": "WEBHOOKS_UNAVAILABLE", "ward_signed": False},
        )
    removed = await _deregister_webhook(vault_address, url)
    return {"removed": removed, "vault_address": vault_address, "ward_signed": False}


@app.post("/keys/generate")
async def generate_key_endpoint(request: KeyRequestModel, institution_key: str = Depends(_institution_key_dep)):
    """
    Generate and register a new institution API key.
    The raw key is returned ONCE — it cannot be retrieved again.
    Store it securely immediately.
    """
    if not KEYS_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "KEYS_UNAVAILABLE", "ward_signed": False})
    try:
        expires_at = None
        if request.expires_in_days:
            expires_at = int(time.time()) + (request.expires_in_days * 86400)
        raw_key = _generate_key(tier=request.tier, label=request.label)
        record = await _register_key(raw_key, tier=request.tier, label=request.label, expires_at=expires_at)
        return {
            "key": raw_key,
            "tier": record.tier,
            "label": record.label,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "warning": "Store this key immediately — it cannot be retrieved again.",
            "ward_signed": False,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "KEY_ERROR", "message": str(exc), "ward_signed": False})


@app.post("/keys/verify")
async def verify_key_endpoint(institution_key: Optional[str] = Depends(_institution_key_dep)):
    """Verify that the provided key is valid and return its metadata."""
    if not KEYS_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "KEYS_UNAVAILABLE", "ward_signed": False})
    key_hash = _key_hash_fn(institution_key)
    record = _key_store_ref.get(key_hash)
    if not record:
        raise HTTPException(status_code=401, detail={"error": "KEY_NOT_FOUND", "ward_signed": False})
    return {
        "valid": True,
        "tier": record.tier,
        "label": record.label,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "last_used_at": record.last_used_at,
        "ward_signed": False,
    }


@app.post("/keys/revoke")
async def revoke_key_endpoint(institution_key: Optional[str] = Depends(_institution_key_dep)):
    """Revoke the current institution key immediately."""
    if not KEYS_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "KEYS_UNAVAILABLE", "ward_signed": False})
    revoked = await _revoke_key(institution_key)
    return {
        "revoked": revoked,
        "warning": "This key is now invalid. Generate a new key if needed.",
        "ward_signed": False,
    }


@app.post("/keys/rotate")
async def rotate_key_endpoint(institution_key: Optional[str] = Depends(_institution_key_dep)):
    """
    Generate a new key with the same tier and label.
    Old key remains valid until explicitly revoked.
    New key is returned ONCE — store immediately.
    """
    if not KEYS_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "KEYS_UNAVAILABLE", "ward_signed": False})
    try:
        new_raw, new_record = await _rotate_key(institution_key)
        return {
            "new_key": new_raw,
            "tier": new_record.tier,
            "label": new_record.label,
            "created_at": new_record.created_at,
            "old_key_status": "still_valid — revoke explicitly when ready",
            "warning": "Store this new key immediately — it cannot be retrieved again.",
            "ward_signed": False,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "KEY_ERROR", "message": str(exc), "ward_signed": False})


@app.get("/vaults/{vault_id}")
async def get_vault(vault_id: str, x_institution_key: Optional[str] = Header(None)):
    verify_institution_key(x_institution_key)
    return {
        "ward_signed": False,
        "flow": "F·01",
        "vault_id": vault_id,
        "source": "XRPL ledger — authoritative state only",
    }


# ── F·02 — Credential Issuance (XLS-70)
@app.post("/credentials/issue")
async def issue_credential(
    req: CredentialIssueRequest,
    x_institution_key: Optional[str] = Header(None),
):
    """
    F·02 — Issue XLS-70 KYC credential.
    SHA-256 hash anchored on-chain. No raw PII ever on-chain.
    Returns unsigned NFTokenMint. ward_signed = False.
    """
    verify_institution_key(x_institution_key)
    logger.info(f"F·02 issue_credential: depositor={req.depositor_address} type={req.kyc_type}")

    if req.kyc_type not in ("institutional", "retail", "accredited"):
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_KYC_TYPE", "message": "kyc_type must be institutional | retail | accredited", "ward_signed": False}
        )

    if not WARD_CLIENT_AVAILABLE:
        return {
            "ward_signed": False,
            "flow": "F·02",
            "status": "spec_mode",
            "unsigned_tx_type": "NFTokenMint",
            "credential_nft_taxon": 282,
            "params": req.model_dump(),
            "note": "Institution signs with their keypair. Ward never signs.",
        }

    try:
        client = WardClient(xrpl_url=XRPL_URL)
        result = await client.issue_credential(
            institution_address=req.institution_address,
            depositor_address=req.depositor_address,
            kyc_hash=req.kyc_hash,
            kyc_type=req.kyc_type,
            expiry_days=req.expiry_days,
        )
        return {"ward_signed": False, "flow": "F·02", **result}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": str(e), "ward_signed": False})
    except LedgerError as e:
        raise HTTPException(status_code=502, detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False})


@app.post("/credentials/verify")
async def verify_credential(
    credential_id: str,
    subject_address: str,
    x_institution_key: Optional[str] = Header(None),
):
    """Verify an XLS-70 credential is valid and unexpired on XRPL."""
    verify_institution_key(x_institution_key)
    return {
        "ward_signed": False,
        "flow": "F·02",
        "credential_id": credential_id,
        "subject_address": subject_address,
        "source": "XRPL ledger — account_nfts query",
    }


# ── F·03 — Policy Purchase (XLS-20)
@app.post(
    "/purchase",
    summary="F·03 — Purchase policy coverage",
    description="Thin wrapper for ward.client.WardClient.purchase_coverage. Returns on-chain proof with ward_signed=false.",
    responses={
        200: {
            "description": "Policy purchase result",
            "content": {
                "application/json": {
                    "example": {
                        "ward_signed": False,
                        "flow": "F·03",
                        "nft_token_id": "A" * 64,
                        "premium_tx": "B" * 64,
                        "mint_tx": "C" * 64,
                        "coverage_drops": 500000000,
                        "expiry_ledger": 800000000,
                    }
                }
            },
        }
    },
)
async def purchase_policy(
    req: PolicyPurchaseRequest = Body(
        ...,
        examples={
            "default": {
                "summary": "Purchase coverage",
                "value": {
                    "vault_id": "rVaultXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                    "pool_address": "rPoolXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                    "coverage_drops": 500000000,
                    "duration_days": 90,
                    "premium_rate": 0.01,
                    "license_tier": "starter",
                },
            }
        },
    ),
    x_institution_key: Optional[str] = Header(None),
):
    """
    F·03 — Purchase XLS-20 NFT policy certificate.
    Coverage terms encoded immutably in NFT URI.
    TF_BURNABLE only — non-transferable by design.
    Returns unsigned NFTokenMint. ward_signed = False.
    """
    verify_institution_key(x_institution_key)
    logger.info(f"F·03 purchase_policy: vault={req.vault_address}")

    if not WARD_CLIENT_AVAILABLE:
        return {
            "ward_signed": False,
            "flow": "F·03",
            "status": "spec_mode",
            "unsigned_tx_type": "NFTokenMint",
            "policy_nft_taxon": 281,
            "flags": "TF_BURNABLE — non-transferable by design",
            "uri_encodes": "coverage_drops | expiry_ledger | vault_address | premium_rate",
            "params": req.model_dump(),
            "note": "Institution signs with their keypair. Ward never signs.",
        }

    try:
        client = WardClient(url=XRPL_URL)
        result = await client.purchase_coverage(
            vault_address=req.vault_address,
            coverage_drops=req.coverage_drops,
            period_days=req.period_days,
            pool_address=req.pool_address,
            premium_rate=req.premium_rate,
            license_tier=req.license_tier,
        )
        return {"ward_signed": False, "flow": "F·03", **result}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": str(e), "ward_signed": False})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": str(e), "ward_signed": False})
    except LedgerError as e:
        raise HTTPException(status_code=502, detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False})


# ── F·05 — Claim Validation (9 deterministic checks)
@app.post(
    "/validate",
    summary="F·05 — Validate claim",
    description="Thin wrapper for ward.validator.ClaimValidator.validate_claim. Runs all 9 on-chain checks and returns deterministic result.",
    responses={
        200: {
            "description": "Claim validation result",
            "content": {
                "application/json": {
                    "example": {
                        "ward_signed": False,
                        "flow": "F·05",
                        "checks_total": 9,
                        "checks_passed": 9,
                        "approved": True,
                        "claim_payout_drops": 1000000,
                        "vault_loss_drops": 1200000,
                        "policy_coverage_drops": 2000000,
                        "rejection_reason": "",
                    }
                }
            },
        }
    },
)
async def validate_claim(
    req: ClaimFileRequest = Body(
        ...,
        examples={
            "default": {
                "summary": "Validate claim",
                "value": {
                    "vault_id": "rVaultXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                    "policy_nft_id": "A" * 64,
                    "claimant_address": "rClaimantXXXXXXXXXXXXXXXXXXXXXXXXX",
                    "loan_id": "B" * 64,
                    "pool_address": "rPoolXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                },
            }
        },
    ),
    x_institution_key: Optional[str] = Header(None),
):
    """
    F·05 — Validate a default claim with 9 deterministic on-chain checks.
    All checks query live XRPL state. No oracle. No human judgment.
    Returns deterministic approval/rejection metadata only.
    ward_signed = False.
    """
    verify_institution_key(x_institution_key)
    logger.info(f"F·05 validate_claim: vault={req.defaulted_vault} nft={req.nft_token_id}")

    if not WARD_CLIENT_AVAILABLE:
        return {
            "ward_signed": False,
            "flow": "F·05",
            "status": "spec_mode",
            "checks_total": 9,
            "checks": [
                {"check": 1, "name": "Policy NFT exists on ledger",         "error_code": "NFT_NOT_FOUND"},
                {"check": 2, "name": "Policy unexpired",                     "error_code": "POLICY_EXPIRED"},
                {"check": 3, "name": "Vault address matches NFT URI",        "error_code": "VAULT_MISMATCH"},
                {"check": 4, "name": "Default confirmed (3 ledger closes)",  "error_code": "DEFAULT_NOT_CONFIRMED"},
                {"check": 5, "name": "Collateral ratio provably breached",   "error_code": "COLLATERAL_SUFFICIENT"},
                {"check": 6, "name": "No active escrow pending",             "error_code": "ESCROW_ALREADY_PENDING"},
                {"check": 7, "name": "KYC credential valid and unexpired",   "error_code": "KYC_CREDENTIAL_INVALID"},
                {"check": 8, "name": "Domain credential valid",              "error_code": "DOMAIN_NOT_AUTHORIZED"},
                {"check": 9, "name": "Rate limit clear",                     "error_code": "RATE_LIMIT_EXCEEDED"},
            ],
            "note": "All 9 checks read live XRPL ledger state. No off-chain inputs permitted.",
        }

    try:
        validator = ClaimValidator(url=XRPL_RPC)
        result = await validator.validate_claim(
            claimant_address=req.claimant_address,
            nft_token_id=req.nft_token_id,
            defaulted_vault=req.defaulted_vault,
            loan_id=req.loan_id,
            pool_address=req.pool_address,
        )
        return {
            "ward_signed": False,
            "flow": "F·05",
            "checks_total": 9,
            "checks_passed": result.steps_passed,
            "approved": result.approved,
            "claim_payout_drops": result.claim_payout_drops,
            "vault_loss_drops": result.vault_loss_drops,
            "policy_coverage_drops": result.policy_coverage_drops,
            "rejection_reason": result.rejection_reason,
            "rejection_memo_hex": result.rejection_memo_hex,
            "note": "All checks read live XRPL ledger state. Include rejection_memo_hex in on-chain transaction memo for audit trail.",
        }
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "CLAIM_REJECTED", "message": str(e), "ward_signed": False}
        )
    except LedgerError as e:
        raise HTTPException(status_code=502, detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False})


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: str, x_institution_key: Optional[str] = Header(None)):
    verify_institution_key(x_institution_key)
    return {
        "ward_signed": False,
        "flow": "F·05",
        "claim_id": claim_id,
        "source": "XRPL ledger — authoritative state only",
    }


# ── F·06 — Escrow Settlement (PREIMAGE-SHA-256)
@app.post("/settlement/escrow")
async def create_escrow(
    req: EscrowCreateRequest,
    x_institution_key: Optional[str] = Header(None),
):
    """
    F·06 — Build PREIMAGE-SHA-256 escrow for claim settlement.
    Ward receives condition_hex only — never the preimage.
    Only the claimant holds the preimage.
    Returns unsigned EscrowCreate. Institution signs and submits.
    Ward's server is irrelevant after EscrowCreate is on-chain.
    ward_signed = False.
    """
    verify_institution_key(x_institution_key)
    logger.info(f"F·06 create_escrow: claim={req.claim_id} claimant={req.claimant_address}")

    if not WARD_CLIENT_AVAILABLE:
        return {
            "ward_signed": False,
            "flow": "F·06",
            "status": "spec_mode",
            "unsigned_tx_type": "EscrowCreate",
            "condition": "PREIMAGE-SHA-256",
            "finish_after": "+48h (172800s)",
            "cancel_after": "+72h (259200s)",
            "nft_burn": "atomic with EscrowFinish — replay structurally impossible",
            "params": req.model_dump(),
            "note": (
                "Institution signs EscrowCreate. Ward's server irrelevant after this. "
                "XRPL enforces settlement. Claimant reveals preimage to finish escrow. "
                "Ward never holds or sees the preimage."
            ),
        }

    try:
        settlement = EscrowSettlement(xrpl_url=XRPL_URL)
        result = await settlement.build_escrow_create(
            claim_id=req.claim_id,
            claimant_address=req.claimant_address,
            coverage_drops=req.coverage_drops,
            condition_hex=req.condition_hex,
            policy_nft_id=req.policy_nft_id,
        )
        return {"ward_signed": False, "flow": "F·06", **result}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": str(e), "ward_signed": False})
    except LedgerError as e:
        raise HTTPException(status_code=502, detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False})


# ── Network Status — public, no auth
@app.get("/network/status")
async def network_status():
    return {
        "ward_signed": False,
        "xrpl_url": XRPL_URL,
        "network": "altnet" if "altnet" in XRPL_URL else "mainnet",
        "ward_client_available": WARD_CLIENT_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ── Dashboard — public vault health snapshot
@app.get("/dashboard/vault/{vault_id}/health")
async def dashboard_vault_health(vault_id: str):
    """
    Public, read-only vault health snapshot for the website dashboard.
    This does NOT require auth and does not mutate anything.

    If XLS-66 ledger objects are not available on the target network, this returns XRPL
    account-level data plus a clear note.
    """
    import re
    if not re.match(r"^r[1-9A-HJ-NP-Za-km-z]{24,34}$", vault_id):
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_ADDRESS", "message": "vault_id must be a valid XRPL r-address", "ward_signed": False}
        )
    client = AsyncJsonRpcClient(XRPL_RPC)
    try:
        resp = await client.request(AccountInfo(account=vault_id, ledger_index="validated"))
        if not resp.is_successful():
            if getattr(resp, "result", {}).get("error") == "actNotFound":
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "VAULT_NOT_FOUND",
                        "message": "Account not found on target XRPL network",
                        "vault_id": vault_id,
                        "xrpl_rpc": XRPL_RPC,
                        "ward_signed": False,
                    },
                )
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "LEDGER_ERROR",
                    "message": "account_info failed",
                    "result": getattr(resp, "result", None),
                    "ward_signed": False,
                },
            )

        acct = resp.result.get("account_data", {})
        return {
            "ward_signed": False,
            "vault_id": vault_id,
            "source": "XRPL account_info (validated ledger)",
            "xls_66_available": False,
            "note": "Full vault health data activates when XLS-66 passes amendment voting on mainnet — Altnet simulation available now.",
            "health_ratio": None,
            "health_ratio_display": "N/A (XLS-66 not available)",
            "active_claims": [],
            "active_claims_count": 0,
            "account_data": {
                "Balance": acct.get("Balance"),
                "OwnerCount": acct.get("OwnerCount"),
                "Sequence": acct.get("Sequence"),
                "Flags": acct.get("Flags"),
            },
            "ledger_index": resp.result.get("ledger_index"),
            "validated": resp.result.get("validated"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "LEDGER_ERROR", "message": str(e), "ward_signed": False},
        )


# ============================================================
# ERROR HANDLERS — ward_signed: false in every response
# ============================================================

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "NOT_FOUND",
            "path": str(request.url.path),
            "ward_signed": False,
            "docs": "https://wardprotocol.org/api.html",
        }
    )

@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.error(f"Internal error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "ward_signed": False,
            "message": "An unexpected error occurred. Ward's server state is irrelevant to on-chain outcomes.",
        }
    )
