"""Verify an upper-bound witness and a closed lower-bound proof, without search."""
import hashlib
import json
from src.api import Position, WorldAction, WorldActionType
from src.framework.generation import canonical
from .model import capture_inputs, initial_state, successors
from .values import ALGORITHM_VERSION, RULES_VERSION, StaticCertificate


def verify_certificate(certificate, level=None):
    """Closure proves no completion cheaper than L; the witness attains L."""
    try:
        if (type(certificate) is not StaticCertificate or type(certificate.allow_wait) is not bool
                or type(certificate.baseline_cost) is not int or certificate.baseline_cost < 1
                or type(certificate.level_bytes) is not bytes or type(certificate.request_bytes) is not bytes
                or type(certificate.rules_version) is not str or type(certificate.algorithm_version) is not str
                or certificate.rules_version != RULES_VERSION or certificate.algorithm_version != ALGORITHM_VERSION
                or type(certificate.witness) is not tuple or type(certificate.labels) is not tuple):
            return False
        record = json.loads(certificate.level_bytes)
        request = json.loads(certificate.request_bytes)
        owned = canonical.read_level(record)
        spec, seed = canonical.read_level_request(request)
        _, _, level_bytes, request_bytes = capture_inputs(owned, spec, seed)
        if level_bytes != certificate.level_bytes or request_bytes != certificate.request_bytes:
            return False
        if level is not None:
            _, _, provided_bytes, _ = capture_inputs(level, spec, seed)
            if provided_bytes != level_bytes:
                return False
        baseline = certificate.baseline_cost
        labels = {}
        for label in certificate.labels:
            if (type(label) is not tuple or len(label) != 5 or any(type(v) is not int for v in label)
                    or label[:4] in labels or not 0 <= label[2] < (1 << len(owned.enemies))
                    or not 0 <= label[3] <= spec.max_turns or not 0 <= label[4] < baseline):
                return False
            if not owned.terrain.is_traversable(Position(label[0], label[1])):
                return False
            if any(not label[2] & (1 << i) and (label[0], label[1]) == (enemy.position.row, enemy.position.column)
                   for i, enemy in enumerate(owned.enemies)):
                return False
            labels[label[:4]] = label[4]
        if labels.get(initial_state(owned)) != 0:
            return False
        for state, cost in labels.items():
            for next_state, action, increment, completed in successors(owned, state, spec.max_turns, certificate.allow_wait):
                next_cost = cost + increment
                if completed and next_cost < baseline:
                    return False
                if not completed and next_cost < baseline and labels.get(next_state, baseline) > next_cost:
                    return False
        state, cost, completed = initial_state(owned), 0, False
        for action in certificate.witness:
            if (completed or type(action) is not WorldAction or type(action.action_type) is not WorldActionType
                    or not any(action.action_type is kind for kind in WorldActionType)
                    or (action.target_id is not None and type(action.target_id) is not str)):
                return False
            matching = [transition for transition in successors(owned, state, spec.max_turns, certificate.allow_wait)
                        if transition[1] == action]
            if len(matching) != 1:
                return False
            state, _, increment, completed = matching[0]
            cost += increment
        return completed and cost == baseline
    except Exception:
        return False

