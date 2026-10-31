"""Instructor-owned synthetic policy and detached run results."""
from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True)
class PatrolPolicy:
    policy_id: str = "DEV-PATROL-FAMILY-B"
    base_points: int = 100
    deduction_rate: int = 2
    zero_score_excess: int = 20

    def __post_init__(self):
        if (type(self.policy_id) is not str or not self.policy_id.startswith("DEV-")
                or self.policy_id != self.policy_id.strip()):
            raise ValueError("DEVELOPMENT_POLICY_REQUIRED")
        for name, minimum in (("base_points", 0), ("deduction_rate", 0), ("zero_score_excess", 1)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError("INVALID_POLICY_VALUE")


@dataclass(frozen=True, slots=True)
class PatrolRun:
    outcome: str
    code: str
    record_bytes: bytes | None = None
    receipt_bytes: bytes | None = None

    @property
    def summary(self):
        """Return a detached report; canonical bytes remain the host evidence."""
        return json.loads(self.record_bytes)["summary"] if self.record_bytes is not None else None


def policy_record(policy):
    if type(policy) is not PatrolPolicy:
        raise ValueError("INVALID_POLICY")
    owned = PatrolPolicy(policy.policy_id, policy.base_points, policy.deduction_rate, policy.zero_score_excess)
    return dict(policy_id=owned.policy_id, base_points=owned.base_points,
                deduction_rate=owned.deduction_rate, zero_score_excess=owned.zero_score_excess,
                development_only=True, scoring_family="B")


from src.framework.generated_static.values import event_metrics
