"""Instructor-owned synthetic policy and detached run results."""
from dataclasses import dataclass
import json


# Instructor-only adapter failures. Existing direct-controller behavior and
# record fields are unchanged; isolated development callbacks retain attribution.
WORKER_FAILURE_CODES = frozenset({
    'WORKER_LAUNCH_ERROR', 'WORKER_EXIT', 'WORKER_TIMEOUT', 'WORKER_OUTPUT_LIMIT',
    'WORKER_PROTOCOL_LIMIT', 'WORKER_PROTOCOL', 'WORKER_STALE_RESPONSE',
    'WORKER_SOURCE_DRIFT', 'WORKER_TEMP_LIMIT', 'WORKER_CLEANUP_ERROR', 'WORKER_HOST_ERROR',
})
SETUP_FAILURE_CODES = frozenset({'CONTROLLER_CONSTRUCTION', 'CONTROLLER_NOT_FRESH'})
CALLBACK_FAILURE_CODES = WORKER_FAILURE_CODES | SETUP_FAILURE_CODES | frozenset({
    'CONTROLLER_CONTRACT', 'CONTROLLER_EXCEPTION',
})


class CallbackFailure(Exception):
    """Bounded instructor adapter failure; never a candidate WorldAction."""
    def __init__(self, code):
        if type(code) is not str or code not in CALLBACK_FAILURE_CODES:
            raise ValueError('INVALID_CALLBACK_FAILURE')
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StaticPolicy:
    policy_id: str = "DEV-FAMILY-B"
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
class StaticRun:
    outcome: str
    code: str
    record_bytes: bytes | None = None
    receipt_bytes: bytes | None = None

    @property
    def summary(self):
        """Return a detached report; canonical bytes remain the host evidence."""
        return json.loads(self.record_bytes)["summary"] if self.record_bytes is not None else None


def policy_record(policy):
    if type(policy) is not StaticPolicy:
        raise ValueError("INVALID_POLICY")
    owned = StaticPolicy(policy.policy_id, policy.base_points, policy.deduction_rate, policy.zero_score_excess)
    return dict(policy_id=owned.policy_id, base_points=owned.base_points,
                deduction_rate=owned.deduction_rate, zero_score_excess=owned.zero_score_excess,
                development_only=True, scoring_family="B")


def event_metrics(events, baseline, policy, completed):
    """Family B from accepted host events, including explicit EXIT in T."""
    accepted = [event for event in events if event["accepted"]]
    turns = len(accepted)
    penalty = sum(event["encounter_penalty"] for event in accepted)
    reward = sum(event["artifact_reward"] for event in accepted)
    cost = turns + penalty
    excess = max(0, cost - baseline)
    defect = completed and cost < baseline
    score = (0 if not completed or defect or excess >= policy.zero_score_excess
             else max(0, policy.base_points + reward - policy.deduction_rate * excess))
    return dict(T=turns, P=penalty, A=reward, C=cost, L=baseline, E=excess, score=score,
                certification_defect=defect)
