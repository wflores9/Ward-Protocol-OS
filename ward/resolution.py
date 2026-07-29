"""Rail-neutral deterministic resolution contracts for Ward Protocol.

The module turns authoritative facts and a fixed rule bundle into a replayable
EvidenceReceipt. It never holds keys, signs, submits, or settles an action.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = "ward-resolution/v1"
ENGINE_VERSION = "0.2.10"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$")
_HEX_64_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_MISSING = object()


class ResolutionError(ValueError):
    """The resolution request violates a deterministic engine contract."""


class ResolutionDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RuleOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    EXISTS = "exists"


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResolutionError(f"{label} must be a non-empty string")


def _require_identifier(value: str, label: str) -> None:
    _require_text(value, label)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ResolutionError(f"{label} contains unsupported characters")


def _require_timestamp(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResolutionError(f"{label} must be a non-negative integer")


def _freeze_json(value: Any, path: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ResolutionError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, Enum):
        return _freeze_json(value.value, path)
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResolutionError(f"{path} keys must be strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(
            _freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value)
        )
    raise ResolutionError(f"{path} contains unsupported type {type(value).__name__}")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Return Ward canonical JSON v1 for deterministic hashing and replay."""

    normalized = _json_value(_freeze_json(value))
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceReference:
    source_id: str
    source_type: str
    locator: str
    observed_at: int
    finality: str
    content_hash: str
    claims: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identifier(self.source_id, "source_id")
        _require_identifier(self.source_type, "source_type")
        _require_text(self.locator, "locator")
        _require_timestamp(self.observed_at, "observed_at")
        _require_identifier(self.finality, "finality")
        if not isinstance(self.content_hash, str) or not _HEX_64_RE.fullmatch(
            self.content_hash
        ):
            raise ResolutionError("content_hash must be a 64-character hex digest")
        object.__setattr__(self, "content_hash", self.content_hash.lower())
        object.__setattr__(self, "claims", _freeze_json(self.claims, "claims"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "locator": self.locator,
            "observed_at": self.observed_at,
            "finality": self.finality,
            "content_hash": self.content_hash,
            "claims": _json_value(self.claims),
        }


@dataclass(frozen=True)
class ResolutionCase:
    case_id: str
    workflow_type: str
    rail: str
    asset_or_obligation: str
    trigger: str
    source_of_truth: str
    rule_bundle_id: str
    signer: str
    requested_action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in (
            "case_id",
            "workflow_type",
            "rail",
            "rule_bundle_id",
            "requested_action",
        ):
            _require_identifier(getattr(self, label), label)
        for label in (
            "asset_or_obligation",
            "trigger",
            "source_of_truth",
            "signer",
        ):
            _require_text(getattr(self, label), label)
        object.__setattr__(self, "metadata", _freeze_json(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "workflow_type": self.workflow_type,
            "rail": self.rail,
            "asset_or_obligation": self.asset_or_obligation,
            "trigger": self.trigger,
            "source_of_truth": self.source_of_truth,
            "rule_bundle_id": self.rule_bundle_id,
            "signer": self.signer,
            "requested_action": self.requested_action,
            "metadata": _json_value(self.metadata),
        }


@dataclass(frozen=True)
class Rule:
    rule_id: str
    field: str
    operator: RuleOperator
    expected: Any
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.rule_id, "rule_id")
        _require_text(self.field, "field")
        try:
            operator = (
                self.operator
                if isinstance(self.operator, RuleOperator)
                else RuleOperator(self.operator)
            )
        except ValueError as exc:
            raise ResolutionError(
                f"unsupported rule operator: {self.operator}"
            ) from exc
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "expected", _freeze_json(self.expected, "expected"))
        if operator is RuleOperator.EXISTS and not isinstance(self.expected, bool):
            raise ResolutionError("exists rules require a boolean expected value")
        refs = tuple(self.evidence_refs)
        if not refs:
            raise ResolutionError("every rule must reference authoritative evidence")
        for source_id in refs:
            _require_identifier(source_id, "evidence_ref")
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "operator": self.operator.value,
            "expected": _json_value(self.expected),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class RuleBundle:
    bundle_id: str
    version: str
    rules: tuple[Rule, ...]
    require_all: bool = True

    def __post_init__(self) -> None:
        _require_identifier(self.bundle_id, "bundle_id")
        _require_identifier(self.version, "version")
        rules = tuple(self.rules)
        if not rules:
            raise ResolutionError("rule bundle must contain at least one rule")
        rule_ids = [rule.rule_id for rule in rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ResolutionError("rule IDs must be unique within a bundle")
        if not isinstance(self.require_all, bool):
            raise ResolutionError("require_all must be boolean")
        object.__setattr__(self, "rules", rules)

    @property
    def reference(self) -> str:
        return f"{self.bundle_id}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "version": self.version,
            "reference": self.reference,
            "require_all": self.require_all,
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True)
class RuleCheck:
    rule_id: str
    field: str
    operator: RuleOperator
    passed: bool
    actual: Any
    expected: Any
    evidence_refs: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        _require_identifier(self.rule_id, "rule_id")
        _require_text(self.field, "field")
        try:
            operator = (
                self.operator
                if isinstance(self.operator, RuleOperator)
                else RuleOperator(self.operator)
            )
        except ValueError as exc:
            raise ResolutionError(
                f"unsupported rule operator: {self.operator}"
            ) from exc
        if not isinstance(self.passed, bool):
            raise ResolutionError("passed must be boolean")
        refs = tuple(self.evidence_refs)
        if not refs:
            raise ResolutionError("every rule check must reference evidence")
        for source_id in refs:
            _require_identifier(source_id, "evidence_ref")
        _require_text(self.detail, "detail")
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "actual", _freeze_json(self.actual, "actual"))
        object.__setattr__(self, "expected", _freeze_json(self.expected, "expected"))
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "operator": self.operator.value,
            "passed": self.passed,
            "actual": _json_value(self.actual),
            "expected": _json_value(self.expected),
            "evidence_refs": list(self.evidence_refs),
            "detail": self.detail,
        }


def _reject_signing_material(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in {
                "privatekey",
                "secret",
                "seed",
                "mnemonic",
                "wardprivatekey",
            }:
                raise ResolutionError(f"{path}.{key} contains prohibited key material")
            if normalized in {
                "signature",
                "txnsignature",
                "signingpubkey",
                "signers",
            } and item not in (None, "", (), [], {}):
                raise ResolutionError(f"{path}.{key} must remain empty and unsigned")
            _reject_signing_material(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_signing_material(item, f"{path}[{index}]")


@dataclass(frozen=True)
class UnsignedAction:
    action_type: str
    rail: str
    signer: str
    payload: Mapping[str, Any]
    ward_signed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.action_type, "action_type")
        _require_identifier(self.rail, "rail")
        _require_text(self.signer, "signer")
        payload = _freeze_json(self.payload, "payload")
        _reject_signing_material(payload)
        object.__setattr__(self, "payload", payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "rail": self.rail,
            "signer": self.signer,
            "payload": _json_value(self.payload),
            "ward_signed": False,
        }


@dataclass(frozen=True)
class EvidenceReceipt:
    case: ResolutionCase
    rule_bundle: RuleBundle
    decision: ResolutionDecision
    checks: tuple[RuleCheck, ...]
    evidence: tuple[EvidenceReference, ...]
    unsigned_actions: tuple[UnsignedAction, ...]
    observed_at: int
    assumptions: tuple[str, ...] = ()
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSION
    ward_signed: bool = field(default=False, init=False)
    _receipt_hash: str = field(init=False, repr=False)
    _receipt_id: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            decision = (
                self.decision
                if isinstance(self.decision, ResolutionDecision)
                else ResolutionDecision(self.decision)
            )
        except ValueError as exc:
            raise ResolutionError(
                f"unsupported resolution decision: {self.decision}"
            ) from exc
        object.__setattr__(self, "decision", decision)
        checks = tuple(self.checks)
        evidence = tuple(self.evidence)
        actions = tuple(self.unsigned_actions)
        assumptions = tuple(self.assumptions)
        if not checks:
            raise ResolutionError("receipt must contain rule checks")
        if not evidence:
            raise ResolutionError("receipt must contain evidence")
        if self.case.rule_bundle_id != self.rule_bundle.reference:
            raise ResolutionError("receipt case does not match its rule bundle")
        expected_rule_ids = tuple(rule.rule_id for rule in self.rule_bundle.rules)
        actual_rule_ids = tuple(check.rule_id for check in checks)
        if actual_rule_ids != expected_rule_ids:
            raise ResolutionError("receipt checks do not match the rule bundle")
        evidence_ids = tuple(item.source_id for item in evidence)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ResolutionError("receipt evidence source IDs must be unique")
        evidence_id_set = set(evidence_ids)
        for check in checks:
            missing_check_refs = tuple(
                source_id
                for source_id in check.evidence_refs
                if source_id not in evidence_id_set
            )
            if missing_check_refs and check.passed:
                raise ResolutionError(
                    "a passing receipt check references missing evidence"
                )
        approved = (
            all(check.passed for check in checks)
            if self.rule_bundle.require_all
            else any(check.passed for check in checks)
        )
        expected_decision = (
            ResolutionDecision.APPROVED if approved else ResolutionDecision.REJECTED
        )
        if decision is not expected_decision:
            raise ResolutionError("receipt decision does not match its rule checks")
        if decision is ResolutionDecision.REJECTED and actions:
            raise ResolutionError("rejected receipts must not contain actions")
        for action in actions:
            if action.signer != self.case.signer:
                raise ResolutionError(
                    "receipt action signer does not match case signer"
                )
            if action.rail != self.case.rail:
                raise ResolutionError("receipt action rail does not match case rail")
            if action.action_type != self.case.requested_action:
                raise ResolutionError(
                    "receipt action type does not match requested action"
                )
        for assumption in assumptions:
            _require_text(assumption, "assumption")
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "unsigned_actions", actions)
        object.__setattr__(self, "assumptions", assumptions)
        _require_timestamp(self.observed_at, "observed_at")
        _require_identifier(self.engine_version, "engine_version")
        _require_identifier(self.schema_version, "schema_version")
        digest = canonical_hash(self._payload_dict())
        object.__setattr__(self, "_receipt_hash", digest)
        object.__setattr__(self, "_receipt_id", f"wr_{digest[:24]}")

    @property
    def receipt_hash(self) -> str:
        return self._receipt_hash

    @property
    def receipt_id(self) -> str:
        return self._receipt_id

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "ward_signed": False,
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "observed_at": self.observed_at,
            "case": self.case.to_dict(),
            "rule_bundle": self.rule_bundle.to_dict(),
            "decision": self.decision.value,
            "checks": [check.to_dict() for check in self.checks],
            "evidence": [item.to_dict() for item in self.evidence],
            "unsigned_actions": [action.to_dict() for action in self.unsigned_actions],
            "assumptions": list(self.assumptions),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "receipt_hash": self.receipt_hash,
            **self._payload_dict(),
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload_dict())


def _lookup(facts: Mapping[str, Any], field_path: str) -> tuple[bool, Any]:
    current: Any = facts
    for segment in field_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False, _MISSING
        current = current[segment]
    return True, current


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(operator: RuleOperator, exists: bool, actual: Any, expected: Any) -> bool:
    if operator is RuleOperator.EXISTS:
        return exists == expected
    if not exists:
        return False
    if operator is RuleOperator.EQ:
        return actual == expected
    if operator is RuleOperator.NE:
        return actual != expected
    if operator in {
        RuleOperator.GT,
        RuleOperator.GTE,
        RuleOperator.LT,
        RuleOperator.LTE,
    }:
        if not _number(actual) or not _number(expected):
            return False
        if operator is RuleOperator.GT:
            return actual > expected
        if operator is RuleOperator.GTE:
            return actual >= expected
        if operator is RuleOperator.LT:
            return actual < expected
        return actual <= expected
    try:
        if operator is RuleOperator.IN:
            return actual in expected
        if operator is RuleOperator.CONTAINS:
            return expected in actual
    except (TypeError, ValueError):
        return False
    return False


class ResolutionEngine:
    """Evaluate fixed rules and emit a replayable, signer-bound receipt."""

    def evaluate(
        self,
        *,
        case: ResolutionCase,
        facts: Mapping[str, Any],
        rule_bundle: RuleBundle,
        evidence: Sequence[EvidenceReference],
        proposed_actions: Sequence[UnsignedAction],
        observed_at: int,
        assumptions: Sequence[str] = (),
    ) -> EvidenceReceipt:
        if case.rule_bundle_id != rule_bundle.reference:
            raise ResolutionError(
                "case rule_bundle_id does not match the supplied rule bundle"
            )
        _require_timestamp(observed_at, "observed_at")
        frozen_facts = _freeze_json(facts, "facts")
        evidence_items = tuple(evidence)
        if not evidence_items:
            raise ResolutionError("at least one evidence reference is required")
        evidence_ids = [item.source_id for item in evidence_items]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ResolutionError("evidence source IDs must be unique")
        evidence_id_set = set(evidence_ids)
        evidence_by_id = {item.source_id: item for item in evidence_items}

        checks: list[RuleCheck] = []
        for rule in rule_bundle.rules:
            missing_refs = tuple(
                source_id
                for source_id in rule.evidence_refs
                if source_id not in evidence_id_set
            )
            exists, actual = _lookup(frozen_facts, rule.field)
            evidence_mismatches: list[str] = []
            if not missing_refs and exists:
                for source_id in rule.evidence_refs:
                    claim_exists, claim_value = _lookup(
                        evidence_by_id[source_id].claims, rule.field
                    )
                    if not claim_exists or not exists or claim_value != actual:
                        evidence_mismatches.append(source_id)
            passed = (
                not missing_refs
                and not evidence_mismatches
                and _compare(rule.operator, exists, actual, rule.expected)
            )
            if missing_refs:
                detail = "missing evidence: " + ", ".join(missing_refs)
            elif evidence_mismatches:
                detail = "evidence claim mismatch: " + ", ".join(evidence_mismatches)
            elif not exists:
                detail = "fact is absent; rule failed closed"
            elif passed:
                detail = "fixed rule matched"
            else:
                detail = "fixed rule did not match"
            checks.append(
                RuleCheck(
                    rule_id=rule.rule_id,
                    field=rule.field,
                    operator=rule.operator,
                    passed=passed,
                    actual=None if actual is _MISSING else actual,
                    expected=rule.expected,
                    evidence_refs=rule.evidence_refs,
                    detail=detail,
                )
            )

        approved = (
            all(check.passed for check in checks)
            if rule_bundle.require_all
            else any(check.passed for check in checks)
        )
        actions = tuple(proposed_actions)
        for action in actions:
            if action.signer != case.signer:
                raise ResolutionError(
                    "unsigned action signer does not match case signer"
                )
            if action.rail != case.rail:
                raise ResolutionError("unsigned action rail does not match case rail")
            if action.ward_signed is not False:
                raise ResolutionError("Ward outputs must remain unsigned")
            if action.action_type != case.requested_action:
                raise ResolutionError(
                    "unsigned action type does not match requested action"
                )

        return EvidenceReceipt(
            case=case,
            rule_bundle=rule_bundle,
            decision=(
                ResolutionDecision.APPROVED if approved else ResolutionDecision.REJECTED
            ),
            checks=tuple(checks),
            evidence=evidence_items,
            unsigned_actions=actions if approved else (),
            observed_at=observed_at,
            assumptions=tuple(assumptions),
        )
