"""Rule-based scene role classifier (T3.1).

Classifies a video scene's role from its motion score, duration, and caption
tags.  Rules are loaded from a YAML config file and cached per path so
repeated calls do not re-read disk.

Output classes: hero | action | transition | detail | establishing | filler | unknown
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Supported condition keys (all others raise ValueError at load time)
# ---------------------------------------------------------------------------
_KNOWN_CONDITION_KEYS: frozenset[str] = frozenset(
    {
        "motion_gte",
        "motion_lt",
        "duration_gte",
        "duration_lt",
        "tags_any",
        "tags_all",
    }
)

# ---------------------------------------------------------------------------
# Default config path (relative to this file's repo root)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_RULES_PATH = _REPO_ROOT / "config" / "enrichment_rules.yaml"


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------
class _Rule:
    """Compiled representation of one entry in ``role_rules``."""

    __slots__ = (
        "role",
        "confidence",
        "motion_gte",
        "motion_lt",
        "duration_gte",
        "duration_lt",
        "tags_any",
        "tags_all",
    )

    def __init__(self, raw: dict[str, Any]) -> None:
        self.role: str = str(raw["role"])
        self.confidence: float = float(raw["confidence"])
        require: dict[str, Any] = raw.get("require", {})

        # Validate keys
        unknown = set(require.keys()) - _KNOWN_CONDITION_KEYS
        if unknown:
            raise ValueError(
                f"Unknown condition key(s) in 'require' for role '{self.role}': "
                f"{', '.join(sorted(unknown))}"
            )

        self.motion_gte: float | None = (
            float(require["motion_gte"]) if "motion_gte" in require else None
        )
        self.motion_lt: float | None = (
            float(require["motion_lt"]) if "motion_lt" in require else None
        )
        self.duration_gte: float | None = (
            float(require["duration_gte"]) if "duration_gte" in require else None
        )
        self.duration_lt: float | None = (
            float(require["duration_lt"]) if "duration_lt" in require else None
        )
        self.tags_any: frozenset[str] = frozenset(require.get("tags_any", []))
        self.tags_all: frozenset[str] = frozenset(require.get("tags_all", []))

    def matches(self, motion: float, duration: float, tags: set[str]) -> bool:
        """Return True if all conditions in this rule are satisfied."""
        if self.motion_gte is not None and motion < self.motion_gte:
            return False
        if self.motion_lt is not None and motion >= self.motion_lt:
            return False
        if self.duration_gte is not None and duration < self.duration_gte:
            return False
        if self.duration_lt is not None and duration >= self.duration_lt:
            return False
        if self.tags_any and not (self.tags_any & tags):
            return False
        if self.tags_all and not self.tags_all.issubset(tags):
            return False
        return True


class _RuleSet:
    """Compiled rule-set loaded from YAML."""

    def __init__(
        self, rules: list[_Rule], fallback_role: str, fallback_confidence: float
    ) -> None:
        self.rules = rules
        self.fallback_role = fallback_role
        self.fallback_confidence = fallback_confidence

    def evaluate(
        self, motion: float, duration: float, tags: set[str]
    ) -> tuple[str, float]:
        for rule in self.rules:
            if rule.matches(motion, duration, tags):
                return rule.role, rule.confidence
        return self.fallback_role, self.fallback_confidence


# ---------------------------------------------------------------------------
# YAML loader (cached per resolved path string)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=32)
def _load_rules(rules_path: str) -> _RuleSet:
    """Load and compile rules from *rules_path*.  Cached per path."""
    with open(rules_path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    raw_rules: list[dict[str, Any]] = data.get("role_rules", [])
    compiled = [_Rule(r) for r in raw_rules]  # raises ValueError on bad keys

    fallback: dict[str, Any] = data.get("fallback", {})
    fallback_role = str(fallback.get("role", "filler"))
    fallback_confidence = float(fallback.get("confidence", 0.3))

    return _RuleSet(compiled, fallback_role, fallback_confidence)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify_role(
    motion: float,
    duration: float,
    tags: set[str],
    rules_path: str | None = None,
) -> tuple[str, float]:
    """Classify the role of a video scene using rule-based logic.

    Parameters
    ----------
    motion:
        Motion score in ``[0.0, 1.0]``.
    duration:
        Scene duration in seconds.
    tags:
        Set of string tags (typically ``ai_caption.tags``).
    rules_path:
        Optional path to a custom YAML file.  When ``None``, the default
        ``config/enrichment_rules.yaml`` (repo root) is used.

    Returns
    -------
    tuple[str, float]
        ``(role, confidence)`` where *role* is one of
        ``hero | action | transition | detail | establishing | filler | unknown``
        and *confidence* is in ``[0.0, 1.0]``.

    Raises
    ------
    ValueError
        If the YAML contains an unknown ``require:`` key.
    """
    resolved = rules_path if rules_path is not None else str(_DEFAULT_RULES_PATH)
    ruleset = _load_rules(resolved)
    return ruleset.evaluate(motion, duration, tags)
