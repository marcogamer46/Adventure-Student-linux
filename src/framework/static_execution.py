"""Shared static execution only; admission and wire trust stay in their wrappers.

Extracted from generated_static.runtime for Task 034. Passive replay never
imports this module and validates history independently of these operations.
"""
from src.api import Position, WorldAction, WorldActionType
from src.framework.static_records import allowed_actions, frame_record, snapshot
from src.framework.generated_static.values import (StaticRun, event_metrics, CallbackFailure,
    WORKER_FAILURE_CODES, SETUP_FAILURE_CODES)

MOVEMENT = {WorldActionType.MOVE_NORTH: (-1, 0), WorldActionType.MOVE_SOUTH: (1, 0),
            WorldActionType.MOVE_WEST: (0, -1), WorldActionType.MOVE_EAST: (0, 1)}


def _owned_action(value):
    try:
        if (type(value) is not WorldAction or type(value.action_type) is not WorldActionType
                or not any(value.action_type is kind for kind in WorldActionType)
                or (value.target_id is not None and type(value.target_id) is not str)):
            return None
        return WorldAction(value.action_type, target_id=value.target_id)
    except (AttributeError, TypeError, ValueError):
        return None


def _apply(level, action, position, collected, defeated, allow_wait):
    """Return one host-owned event effect; rejected actions have no effects."""
    kind, target = action.action_type, action.target_id
    destination, reward, penalty, artifact, enemy, completed = position, 0, 0, None, None, False
    code = "OK"
    if kind not in allowed_actions(allow_wait):
        code = "ACTION_DISABLED"
    elif kind not in (WorldActionType.COLLECT, WorldActionType.ENGAGE) and target is not None:
        code = "UNEXPECTED_TARGET"
    elif kind in MOVEMENT:
        dr, dc = MOVEMENT[kind]
        proposed = (position[0] + dr, position[1] + dc)
        if not level.terrain.is_traversable(Position(*proposed)):
            code = "BLOCKED_TERRAIN"
        elif any(e.enemy_id not in defeated and (e.position.row, e.position.column) == proposed for e in level.enemies):
            code = "BLOCKED_ENEMY"
        else:
            destination = proposed
    elif kind is WorldActionType.COLLECT:
        found = next((a for a in level.artifacts if a.artifact_id == target), None)
        if found is None or target in collected or (found.position.row, found.position.column) != position:
            code = "INVALID_ARTIFACT"
        else:
            reward, artifact = found.value, found.artifact_id
    elif kind is WorldActionType.ENGAGE:
        found = next((e for e in level.enemies if e.enemy_id == target), None)
        if (found is None or target in defeated
                or abs(found.position.row - position[0]) + abs(found.position.column - position[1]) != 1):
            code = "INVALID_ENEMY"
        else:
            penalty, enemy = found.encounter_penalty, found.enemy_id
    elif kind is WorldActionType.EXIT:
        if position != (level.exit.row, level.exit.column):
            code = "NOT_AT_EXIT"
        else:
            completed = True
    return code, destination, reward, penalty, artifact, enemy, completed


def run_history(level, cap, allow_wait, baseline, policy, admission, controller, build_record,
                snapshot_factory=snapshot, action_owner=_owned_action, apply_action=_apply):
    position, turn, collected, defeated = (level.start.row, level.start.column), 0, set(), set()
    events, frames = [], []
    def frame():
        return snapshot_factory(level, policy, baseline, cap, allow_wait, position, turn, collected, defeated)
    frames.append(frame_record(frame()))
    try:
        callback = getattr(controller, "choose_action")
        entry_error = None if callable(callback) else "CONTROLLER_CONTRACT"
    except AttributeError:
        callback, entry_error = None, "CONTROLLER_CONTRACT"
    except Exception:
        callback, entry_error = None, "CONTROLLER_EXCEPTION"
    completed, code = False, None
    while turn < cap:
        action = None
        if entry_error is not None:
            code = entry_error
        else:
            student_frame = frame()
            agent_id = level.character.agent_id
            try:
                returned = callback(student_frame, agent_id)
            except CallbackFailure as failure:
                code = failure.code
            except Exception:
                code = "CONTROLLER_EXCEPTION"
            else:
                action = action_owner(returned)
                code = "MALFORMED_ACTION" if action is None else "OK"
        destination, reward, penalty, artifact, enemy = position, 0, 0, None, None
        if action is not None:
            code, destination, reward, penalty, artifact, enemy, completed = apply_action(
                level, action, position, collected, defeated, allow_wait)
        accepted = code == "OK"
        events.append(dict(attempt=len(events) + 1, accepted=accepted, code=code,
            action=None if action is None else dict(action_type=action.action_type.value, target_id=action.target_id),
            turn_before=turn, turn_after=turn + int(accepted), position_before=list(position),
            position_after=list(destination), artifact_reward=reward, encounter_penalty=penalty,
            collected_artifact_id=artifact, defeated_enemy_id=enemy))
        if accepted:
            position, turn = destination, turn + 1
            if artifact is not None:
                collected.add(artifact)
            if enemy is not None:
                defeated.add(enemy)
        frames.append(frame_record(frame()))
        if completed or not accepted:
            break
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
    record_bytes, receipt_bytes = build_record(admission, events, frames, summary)
    return StaticRun(outcome, final_code, record_bytes, receipt_bytes)
