"""Exact Dijkstra over position, defeated set and accepted-turn count."""
import heapq
import math
import time
from src.framework.generation.canonical import CanonicalError
from src.framework.level_patrol_validation import LevelPatrolValidationError
from .model import capture_inputs, initial_state, successors
from .proof import verify_certificate
from .values import CertificationResult, SearchBudget, StaticCertificate, StaticRules


def _configuration(rules, budget):
    try:
        if type(rules) is not StaticRules or type(rules.allow_wait) is not bool or type(budget) is not SearchBudget:
            return False
        if any(type(value) is not int or value < 0 for value in (budget.max_expansions, budget.max_states)):
            return False
        return budget.max_seconds is None or (type(budget.max_seconds) in (int, float)
                                             and math.isfinite(budget.max_seconds) and budget.max_seconds > 0)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False


def certify_static(level, specification, original_seed, *, rules=StaticRules(), budget=SearchBudget()):
    if not _configuration(rules, budget):
        return CertificationResult("HOST_ERROR", "INVALID_CONFIGURATION")
    try:
        level, specification, level_bytes, request_bytes = capture_inputs(level, specification, original_seed)
    except (CanonicalError, LevelPatrolValidationError):
        return CertificationResult("INVALID_INPUT", "INVALID_STATIC_INPUT")
    except Exception:
        return CertificationResult("HOST_ERROR", "VALIDATION_ERROR")
    try:
        return _search(level, specification, level_bytes, request_bytes, rules, budget)
    except Exception:
        return CertificationResult("HOST_ERROR", "SEARCH_ERROR")


def _search(level, spec, level_bytes, request_bytes, rules, budget, verifier=verify_certificate):
    start = initial_state(level)
    distances, parents, labels = {start: 0}, {}, {}
    queue, sequence = [(0, 0, start)], 0
    best, witness = None, None
    begun = time.monotonic()
    while queue:
        if best is not None and queue[0][0] >= best:
            break
        cost, _, state = heapq.heappop(queue)
        if distances[state] != cost or state in labels:
            continue
        if (len(labels) >= budget.max_expansions or len(distances) > budget.max_states
                or (budget.max_seconds is not None and time.monotonic() - begun >= budget.max_seconds)):
            return CertificationResult("INCONCLUSIVE", "SEARCH_BUDGET", expanded_states=len(labels), discovered_states=len(distances))
        labels[state] = cost
        for next_state, action, increment, completed in successors(level, state, spec.max_turns, rules.allow_wait):
            next_cost = cost + increment
            if completed:
                if best is None or next_cost < best:
                    best = next_cost
                    actions, cursor = [action], state
                    while cursor != start:
                        cursor, previous = parents[cursor]
                        actions.append(previous)
                    witness = tuple(reversed(actions))
                continue
            if best is not None and next_cost >= best:
                continue
            if next_cost < distances.get(next_state, next_cost + 1):
                if next_state not in distances and len(distances) >= budget.max_states:
                    return CertificationResult("INCONCLUSIVE", "SEARCH_BUDGET", expanded_states=len(labels), discovered_states=len(distances))
                distances[next_state], parents[next_state] = next_cost, (state, action)
                sequence += 1
                heapq.heappush(queue, (next_cost, sequence, next_state))
    if budget.max_seconds is not None and time.monotonic() - begun >= budget.max_seconds:
        return CertificationResult("INCONCLUSIVE", "SEARCH_BUDGET", expanded_states=len(labels), discovered_states=len(distances))
    if best is None:
        return CertificationResult("PROVEN_UNSOLVABLE", "NO_COMPLETION_WITHIN_H", expanded_states=len(labels), discovered_states=len(distances))
    certificate = StaticCertificate(level_bytes, request_bytes, rules.allow_wait, best, witness,
                                    tuple((*state, cost) for state, cost in sorted(labels.items()) if cost < best))
    if not verifier(certificate):
        return CertificationResult("HOST_ERROR", "PROOF_ERROR", expanded_states=len(labels), discovered_states=len(distances))
    if budget.max_seconds is not None and time.monotonic() - begun >= budget.max_seconds:
        return CertificationResult("INCONCLUSIVE", "SEARCH_BUDGET", expanded_states=len(labels), discovered_states=len(distances))
    return CertificationResult("CERTIFIED", "OK", certificate, len(labels), len(distances))
