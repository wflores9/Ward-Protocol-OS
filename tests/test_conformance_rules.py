from __future__ import annotations

from pathlib import Path

from ward.conformance_rules import CHECK_LABELS, WARD_CONFORMANCE_RULES


def test_conformance_rules_cover_exactly_nine_steps() -> None:
    assert [rule["number"] for rule in WARD_CONFORMANCE_RULES] == list(range(1, 10))
    assert set(CHECK_LABELS) == set(range(1, 10))


def test_conformance_rule_labels_match_public_spec() -> None:
    spec = Path("docs/pilots/ward-semantic-check-rules.md").read_text(
        encoding="utf-8"
    )

    for rule in WARD_CONFORMANCE_RULES:
        assert rule["label"] in spec


def test_step_nine_is_pool_solvency_and_rate_limit() -> None:
    step_nine = WARD_CONFORMANCE_RULES[8]

    assert step_nine["number"] == 9
    assert step_nine["label"] == "Pool solvency and rate limits"
    assert "3" in step_nine["deterministic_rule"]
    assert "300" in step_nine["deterministic_rule"]
    assert "1.5" in step_nine["deterministic_rule"]
