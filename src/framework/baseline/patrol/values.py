"""Canonical timing rules and immutable proof data."""
from dataclasses import dataclass
import json
from src.api import WorldAction
from src.framework.baseline.static.values import CertificationResult, SearchBudget

RULES_VERSION = "development-instructor-patrol-1"
ALGORITHM_VERSION = "dijkstra-patrol-position-static-defeats-turn-1"


@dataclass(frozen=True, slots=True)
class PatrolRules:
    allow_wait: bool = True
    allow_collect: bool = True
    allow_engage: bool = True
    deadline_turn: int | None = None


def rules_record(rules, max_turns):
    if (type(rules) is not PatrolRules or type(max_turns) is not int or max_turns < 1
            or any(type(v) is not bool for v in (rules.allow_wait, rules.allow_collect, rules.allow_engage))
            or (rules.deadline_turn is not None and
                (type(rules.deadline_turn) is not int or not 0 < rules.deadline_turn < max_turns))):
        raise ValueError("INVALID_TIMING_RULES")
    return dict(allow_wait=rules.allow_wait, allow_collect=rules.allow_collect,
                allow_engage=rules.allow_engage, deadline_turn=rules.deadline_turn)


def encode_rules(rules, max_turns):
    return json.dumps(rules_record(rules, max_turns), sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PatrolCertificate:
    level_bytes: bytes
    request_bytes: bytes
    rules_bytes: bytes
    baseline_cost: int
    witness: tuple[WorldAction, ...]
    # row, column, static-defeat mask, elapsed accepted turns, distance label
    labels: tuple[tuple[int, int, int, int, int], ...]
    rules_version: str = RULES_VERSION
    algorithm_version: str = ALGORITHM_VERSION
