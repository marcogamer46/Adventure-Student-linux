"""Format-neutral passive static history checks; no execution or certification imports.

Task 034 extracts existing generated-static checks unchanged. Legacy wrappers
retain independent receipt admission; public practice supplies analytic admission.
"""
from dataclasses import dataclass
import hashlib
import json
from src.api import EnemyObservation, Position, WorldAction, WorldActionType, WorldSnapshot
from src.framework.generation import canonical
from src.framework.generated_static.values import (event_metrics, WORKER_FAILURE_CODES,
    SETUP_FAILURE_CODES, CALLBACK_FAILURE_CODES)
MAX_RECORD_BYTES = 16 * 1024 * 1024
EVENT_FIELDS = ("attempt", "accepted", "code", "action", "turn_before", "turn_after", "position_before",
                "position_after", "artifact_reward", "encounter_penalty", "collected_artifact_id", "defeated_enemy_id")
MOVES = {"MOVE_NORTH": (-1, 0), "MOVE_SOUTH": (1, 0), "MOVE_WEST": (0, -1), "MOVE_EAST": (0, 1)}


class ReplayError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def _keys(value, expected):
    if type(value) is not dict or any(type(k) is not str for k in value) or set(value) != set(expected):
        raise ReplayError("INVALID_SCHEMA")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError("DUPLICATE_KEY")
        result[key] = value
    return result


def read_json(raw):
    if type(raw) is not bytes or len(raw) > MAX_RECORD_BYTES:
        raise ReplayError("INVALID_BYTES")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ReplayError("NONFINITE_VALUE")))
        canonical.validate_json_depth(value)
        if encode(value) != raw:
            raise ReplayError("NONCANONICAL_RECORD")
        return value
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError, RecursionError) as error:
        if isinstance(error, ReplayError):
            raise
        raise ReplayError("INVALID_JSON") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def allowed_actions(allow_wait):
    return tuple(kind for kind in WorldActionType
                 if kind is not WorldActionType.INTERACT and (allow_wait or kind is not WorldActionType.WAIT))


def snapshot(level, policy, baseline, max_turns, allow_wait, position, turn, collected, defeated):
    """Every frame owns its initial definitions, including all static observations."""
    owned = canonical.read_level(canonical.level_record(level))
    return WorldSnapshot(level=owned, agent_position=Position(*position), turn=turn,
        collected_artifact_ids=tuple(sorted(collected)), defeated_enemy_ids=tuple(sorted(defeated)),
        base_points=policy.base_points, deduction_rate=policy.deduction_rate, baseline_cost=baseline,
        zero_score_excess=policy.zero_score_excess, max_turns=max_turns, deadline_turn=None,
        allowed_actions=allowed_actions(allow_wait), enemy_observations=tuple(
            EnemyObservation(enemy_id=enemy.enemy_id, position=None if enemy.enemy_id in defeated else enemy.position,
                             phase=None) for enemy in owned.enemies))


def frame_record(frame):
    return dict(level_sha256=canonical.digest(canonical.level_record(frame.level)),
        agent_position=[frame.agent_position.row, frame.agent_position.column], turn=frame.turn,
        collected_artifact_ids=list(frame.collected_artifact_ids), defeated_enemy_ids=list(frame.defeated_enemy_ids),
        base_points=frame.base_points, deduction_rate=frame.deduction_rate, baseline_cost=frame.baseline_cost,
        zero_score_excess=frame.zero_score_excess, max_turns=frame.max_turns, deadline_turn=frame.deadline_turn,
        allowed_actions=[kind.value for kind in frame.allowed_actions], enemy_observations=[
            dict(enemy_id=observation.enemy_id, position=None if observation.position is None else
                 [observation.position.row, observation.position.column], phase=observation.phase)
            for observation in frame.enemy_observations])


@dataclass(frozen=True, slots=True)
class ReplayView:
    snapshots: tuple[WorldSnapshot, ...]
    summary_bytes: bytes

    @property
    def summary(self):
        return json.loads(self.summary_bytes)


def _action(value):
    value = _keys(value, ("action_type", "target_id"))
    if type(value["action_type"]) is not str or (value["target_id"] is not None and type(value["target_id"]) is not str):
        raise ReplayError("INVALID_ACTION_RECORD")
    try:
        action = WorldAction(WorldActionType(value["action_type"]), target_id=value["target_id"])
    except (TypeError, ValueError):
        raise ReplayError("INVALID_ACTION_RECORD") from None
    return action


def _check_event(event, index, level, allow_wait, position, turn, collected, defeated):
    """Check stored event relationships; never call a runtime step or component."""
    event = _keys(event, EVENT_FIELDS)
    action = None if event["action"] is None else _action(event["action"])
    next_position, reward, penalty, artifact, enemy, completed = position, 0, 0, None, None, False
    if action is None:
        if type(event["code"]) is not str or (event["code"] != "MALFORMED_ACTION" and event["code"] not in CALLBACK_FAILURE_CODES):
            raise ReplayError("INVALID_EVENT")
        if (event["code"] == "CONTROLLER_CONTRACT" or event["code"] in SETUP_FAILURE_CODES) and index != 1:
            raise ReplayError("INVALID_EVENT")
        code = event["code"]
    else:
        kind, target = action.action_type.value, action.target_id
        if action.action_type not in allowed_actions(allow_wait):
            code = "ACTION_DISABLED"
        elif kind not in ("COLLECT", "ENGAGE") and target is not None:
            code = "UNEXPECTED_TARGET"
        elif kind in MOVES:
            delta = MOVES[kind]
            destination = (position[0] + delta[0], position[1] + delta[1])
            if not level.terrain.is_traversable(Position(*destination)):
                code = "BLOCKED_TERRAIN"
            elif any(e.enemy_id not in defeated and (e.position.row, e.position.column) == destination for e in level.enemies):
                code = "BLOCKED_ENEMY"
            else:
                code, next_position = "OK", destination
        elif kind == "COLLECT":
            found = next((a for a in level.artifacts if a.artifact_id == target and a.artifact_id not in collected
                          and (a.position.row, a.position.column) == position), None)
            if found is None:
                code = "INVALID_ARTIFACT"
            else:
                code, artifact, reward = "OK", found.artifact_id, found.value
        elif kind == "ENGAGE":
            found = next((e for e in level.enemies if e.enemy_id == target and e.enemy_id not in defeated
                          and abs(e.position.row - position[0]) + abs(e.position.column - position[1]) == 1), None)
            if found is None:
                code = "INVALID_ENEMY"
            else:
                code, enemy, penalty = "OK", found.enemy_id, found.encounter_penalty
        elif kind == "EXIT":
            completed = position == (level.exit.row, level.exit.column)
            code = "OK" if completed else "NOT_AT_EXIT"
        else:
            code = "OK"  # WAIT, already checked against the admitted action model.
    accepted = code == "OK"
    expected = dict(attempt=index, accepted=accepted, code=code, action=event["action"], turn_before=turn,
        turn_after=turn + int(accepted), position_before=list(position), position_after=list(next_position),
        artifact_reward=reward, encounter_penalty=penalty, collected_artifact_id=artifact, defeated_enemy_id=enemy)
    if encode(event) != encode(expected):
        raise ReplayError("EVENT_MISMATCH")
    if artifact is not None:
        collected.add(artifact)
    if enemy is not None:
        defeated.add(enemy)
    return next_position, turn + int(accepted), completed, accepted, code


def validate_history(record, level, policy, baseline, cap, allow_wait):
    events, frames = record["events"], record["frames"]
    if (type(events) is not list or not 1 <= len(events) <= cap or type(frames) is not list
            or len(frames) != len(events) + 1):
        raise ReplayError("INVALID_HISTORY")
    position, turn, collected, defeated = (level.start.row, level.start.column), 0, set(), set()
    snapshots = [snapshot(level, policy, baseline, cap, allow_wait, position, turn, collected, defeated)]
    terminal, completed, code = False, False, None
    for index, event in enumerate(events, 1):
        if terminal:
            raise ReplayError("EVENT_AFTER_TERMINATION")
        position, turn, completed, accepted, code = _check_event(event, index, level, allow_wait, position, turn, collected, defeated)
        terminal = completed or not accepted or turn >= cap
        snapshots.append(snapshot(level, policy, baseline, cap, allow_wait, position, turn, collected, defeated))
    if not terminal:
        raise ReplayError("TRUNCATED_HISTORY")
    if encode(frames) != encode([frame_record(frame) for frame in snapshots]):
        raise ReplayError("FRAME_MISMATCH")
    metrics = event_metrics(events, baseline, policy, completed)
    if metrics["certification_defect"]:
        outcome, final_code = "HOST_CERTIFICATION_DEFECT", "C_BELOW_L"
    elif completed:
        outcome, final_code = "COMPLETED", "EXIT"
    elif code in WORKER_FAILURE_CODES:
        outcome, final_code = "WORKER_ERROR", code
    elif code in ("CONTROLLER_EXCEPTION", "CONTROLLER_CONTRACT") or code in SETUP_FAILURE_CODES:
        outcome, final_code = "CONTROLLER_ERROR", code
    elif code != "OK":
        outcome, final_code = "ILLEGAL_ACTION", code
    else:
        outcome, final_code = "TURN_LIMIT", "MAX_TURNS"
    summary = dict(outcome=outcome, code=final_code, completed=completed, max_turns=cap, **metrics)
    if encode(record["summary"]) != encode(summary):
        raise ReplayError("SUMMARY_MISMATCH")
    return ReplayView(tuple(snapshots), encode(summary))
