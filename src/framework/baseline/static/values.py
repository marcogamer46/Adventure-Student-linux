"""Immutable search inputs, detached proof data and finite outcomes."""
from dataclasses import dataclass
from src.api import WorldAction

OUTCOMES = frozenset({"CERTIFIED", "PROVEN_UNSOLVABLE", "INCONCLUSIVE", "INVALID_INPUT", "HOST_ERROR"})
RULES_VERSION = "development-static-no-collection-1"
ALGORITHM_VERSION = "dijkstra-position-defeated-turn-1"


@dataclass(frozen=True, slots=True)
class StaticRules:
    allow_wait: bool = True


@dataclass(frozen=True, slots=True)
class SearchBudget:
    max_expansions: int = 100_000
    max_states: int = 250_000
    max_seconds: float | None = 10.0


@dataclass(frozen=True, slots=True)
class StaticCertificate:
    """Host-derived witness and lower-bound closure; no student implementation."""
    level_bytes: bytes
    request_bytes: bytes
    allow_wait: bool
    baseline_cost: int
    witness: tuple[WorldAction, ...]
    # row, column, defeated bitmask, elapsed accepted turns, distance label
    labels: tuple[tuple[int, int, int, int, int], ...]
    rules_version: str = RULES_VERSION
    algorithm_version: str = ALGORITHM_VERSION


@dataclass(frozen=True, slots=True)
class CertificationResult:
    outcome: str
    code: str
    certificate: StaticCertificate | None = None
    expanded_states: int = 0
    discovered_states: int = 0

    @property
    def baseline_cost(self):
        return self.certificate.baseline_cost if self.certificate is not None else None
