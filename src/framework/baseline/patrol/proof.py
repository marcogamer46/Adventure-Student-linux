"""Independently check patrol witness and lower-bound closure without search."""
import hashlib
import json
from src.api import WorldAction, WorldActionType
from src.framework.generation import canonical
from .model import capture_inputs, initial_state, state_valid, successors
from .values import ALGORITHM_VERSION, RULES_VERSION, PatrolCertificate, PatrolRules, encode_rules, rules_record


def verify_certificate(certificate, level=None, specification=None, original_seed=None, rules=None):
    try:
        if (type(certificate) is not PatrolCertificate or type(certificate.baseline_cost) is not int
                or certificate.baseline_cost < 1 or type(certificate.witness) is not tuple or type(certificate.labels) is not tuple
                or any(type(v) is not bytes for v in (certificate.level_bytes, certificate.request_bytes, certificate.rules_bytes))
                or type(certificate.rules_version) is not str or certificate.rules_version != RULES_VERSION
                or type(certificate.algorithm_version) is not str or certificate.algorithm_version != ALGORITHM_VERSION):
            return False
        owned = canonical.read_level(json.loads(certificate.level_bytes))
        spec, seed = canonical.read_level_request(json.loads(certificate.request_bytes))
        owned, spec, level_bytes, request_bytes = capture_inputs(owned, spec, seed)
        timing = PatrolRules(**json.loads(certificate.rules_bytes))
        rules_bytes = encode_rules(timing, spec.max_turns)
        if (level_bytes != certificate.level_bytes or request_bytes != certificate.request_bytes
                or rules_bytes != certificate.rules_bytes):
            return False
        if level is not None and capture_inputs(level, spec, seed)[2] != level_bytes:
            return False
        if (specification is not None or original_seed is not None) and canonical.canonical_bytes(
                canonical.level_request(specification, original_seed)) != request_bytes:
            return False
        if rules is not None and encode_rules(rules, spec.max_turns) != rules_bytes:
            return False
        baseline, labels = certificate.baseline_cost, {}
        for label in certificate.labels:
            if (type(label) is not tuple or len(label) != 5 or any(type(v) is not int for v in label)
                    or label[:4] in labels or not 0 <= label[2] < 1 << len(owned.enemies)
                    or not 0 <= label[4] < baseline or not state_valid(owned, label[:4], spec.max_turns, timing)):
                return False
            labels[label[:4]] = label[4]
        if labels.get(initial_state(owned)) != 0:
            return False
        for state, cost in labels.items():
            for next_state, _, increment, completed in successors(owned, state, spec.max_turns, timing):
                next_cost = cost + increment
                if completed and next_cost < baseline:
                    return False
                if not completed and next_cost < baseline and labels.get(next_state, baseline) > next_cost:
                    return False
        state, cost, completed = initial_state(owned), 0, False
        for action in certificate.witness:
            if (completed or type(action) is not WorldAction or type(action.action_type) is not WorldActionType
                    or not any(action.action_type is k for k in WorldActionType)
                    or (action.target_id is not None and type(action.target_id) is not str)):
                return False
            matching = [t for t in successors(owned, state, spec.max_turns, timing) if t[1] == action]
            if len(matching) != 1:
                return False
            state, _, increment, completed = matching[0]
            cost += increment
        return completed and cost == baseline
    except Exception:
        return False

