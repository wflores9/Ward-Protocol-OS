"""Gate A provenance and policy pins for certificate issuance/resolution.

Issuance helpers fail-closed for NEW certificates. ClaimValidator /
ResolutionEngine stamp best-effort pins on receipts (env fallback OK).
Missing pins on already-indexed certs remain grandfathered (load returns
None; no invent).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ward.conformance_rules import (
    COVENANT_RULE_SET_VERSION,
    ConformanceRuleSet,
    load_conformance_rule_set,
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
logger = logging.getLogger("ward.certificate_pins")


def resolver_commit_sha(repo_root: Path) -> str:
    """Return the SHA of the resolver checkout, failing closed if unavailable."""

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "resolver git commit is unavailable; refusing issuance"
        ) from exc
    sha = proc.stdout.strip().lower()
    if not _GIT_SHA_RE.fullmatch(sha):
        raise RuntimeError("resolver git commit is invalid; refusing issuance")
    return sha


def resolve_resolver_commit_sha(repo_root: Path | None = None) -> str:
    """Best-effort resolver SHA for validation/receipt stamps.

    Tries ``resolver_commit_sha``; on RuntimeError falls back to
    ``WARD_RESOLVER_COMMIT_SHA``. Returns "" if still unavailable.
    Issuance paths must keep using ``resolver_commit_sha`` /
    ``require_new_certificate_pins`` (fail-closed).
    """

    root = repo_root or Path(__file__).resolve().parents[1]
    try:
        return resolver_commit_sha(root)
    except RuntimeError as exc:
        logger.warning("resolver commit unavailable via git: %s", exc)
    env_sha = (os.getenv("WARD_RESOLVER_COMMIT_SHA") or "").strip().lower()
    if _GIT_SHA_RE.fullmatch(env_sha):
        return env_sha
    if env_sha:
        logger.warning("WARD_RESOLVER_COMMIT_SHA is not a valid 40-character SHA")
    return ""


def stamp_new_certificate(
    certificate: dict[str, Any],
    *,
    resolver_sha: str,
    rule_set_version: str = COVENANT_RULE_SET_VERSION,
    resolver_build_digest: str | None = None,
) -> ConformanceRuleSet:
    """Stamp distinct resolver/ruleset pins without changing top-level ``commit``."""

    normalized_sha = (
        resolver_sha.strip().lower() if isinstance(resolver_sha, str) else ""
    )
    if not _GIT_SHA_RE.fullmatch(normalized_sha):
        raise ValueError("resolver_commit_sha must be a full 40-character git SHA")
    rule_set = load_conformance_rule_set(rule_set_version)
    certificate["resolver_commit_sha"] = normalized_sha
    certificate["covenant_rule_set_version"] = rule_set.version
    if resolver_build_digest is not None:
        if (
            not isinstance(resolver_build_digest, str)
            or not resolver_build_digest.strip()
        ):
            raise ValueError("resolver_build_digest must be a non-empty string")
        certificate["resolver_build_digest"] = resolver_build_digest.strip()
    return rule_set


def is_legacy_certificate(certificate: dict[str, Any]) -> bool:
    """Recognize explicitly legacy records; never infer or invent their pins."""

    return (
        certificate.get("legacy") is True
        or certificate.get("legacy_pre_archive") is True
    )


def load_certificate_rule_set(
    certificate: dict[str, Any],
    *,
    require_pin: bool = False,
) -> ConformanceRuleSet | None:
    """Load the certificate's pinned ruleset, never the current default.

    Missing ``covenant_rule_set_version`` is grandfathered without inventing
    pins (absence is not the same as ``legacy=true``). That keeps live
    operator receipts such as WARD-DEVNET-20260901-001 /
    WARD-DEVNET-20260902-001 resolvable without rewriting certificate JSON.
    New issuance must use ``stamp_new_certificate`` /
    ``require_new_certificate_pins`` so pins are present and fail-closed.
    """

    version = certificate.get("covenant_rule_set_version")
    if version in (None, ""):
        if require_pin:
            raise ValueError("covenant_rule_set_version is required for resolution")
        # Grandfather: do not invent pins for indexed certs that predate Gate A.
        return None
    if not isinstance(version, str):
        raise ValueError("covenant_rule_set_version must be a string")
    return load_conformance_rule_set(version)


def require_new_certificate_pins(
    certificate: dict[str, Any],
) -> ConformanceRuleSet:
    """Validate both Gate A pins before issuing a new certificate."""

    sha = certificate.get("resolver_commit_sha")
    if not isinstance(sha, str) or not _GIT_SHA_RE.fullmatch(sha.lower()):
        raise ValueError("resolver_commit_sha is required for new certificates")
    rule_set = load_certificate_rule_set(certificate, require_pin=True)
    assert rule_set is not None
    return rule_set
