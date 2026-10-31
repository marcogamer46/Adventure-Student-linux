"""Passive public-practice presentation; no legacy/instructor loader dependencies."""
import hashlib
import json
from .model import DIRECTIONS, Entity, Frame, Recording, heading, pose_for
PUBLIC = "ultra-workbench-public-run"
PUBLIC_PROJECT = "ultra-public-project-run"
PATROL = "ultra-development-instructor-patrol-run"

class PresentationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def cell(position): return (position.row, position.column)


def _presentation_bounds(snapshots):
    if len(snapshots) > 20000: raise PresentationError("VIEWER_FRAME_LIMIT")
    terrain = snapshots[0].level.terrain
    if terrain.rows > 128 or terrain.columns > 128: raise PresentationError("VIEWER_BOARD_LIMIT")


def _entities(snapshot, previous=None):
    artifacts = tuple(Entity(a.artifact_id, cell(a.position), a.value) for a in snapshot.level.artifacts
                      if a.artifact_id not in snapshot.collected_artifact_ids)
    observations = {o.enemy_id: o for o in snapshot.enemy_observations}
    old = {} if previous is None else {e.entity_id: e for e in previous.enemies}
    patrol_ids = {p.enemy_id for p in snapshot.level.patrols}
    enemies = []
    for e in snapshot.level.enemies:
        observation = observations[e.enemy_id]
        if observation.position is None: continue
        position = cell(observation.position)
        direction = heading(old[e.enemy_id].position, position, old[e.enemy_id].direction) if e.enemy_id in old else "south"
        enemies.append(Entity(e.enemy_id, position, e.encounter_penalty, e.enemy_id in patrol_ids, observation.phase, direction))
    return artifacts, tuple(enemies)


def recording_from_view(raw, view, data, title, kind):
    snapshots = view.snapshots
    _presentation_bounds(snapshots)
    summary = view.summary
    frames, visited, direction = [], set(), "south"
    for i, snapshot in enumerate(snapshots):
        position = cell(snapshot.agent_position)
        visited.add(position)
        event = None if i == 0 else data["events"][i - 1]
        action = "READY" if event is None else (event["action"]["action_type"] if event["action"] else "CALLBACK")
        accepted = None if event is None else event["accepted"]
        if accepted: direction = DIRECTIONS.get(action, direction)
        terminal = i == len(snapshots) - 1
        completed = terminal and summary["completed"]
        status = summary["outcome"] if terminal else "RUNNING"
        reason = summary["code"] if terminal else ""
        target = None if event is None or event["action"] is None else event["action"]["target_id"]
        lines = ["Initial recorded state."]
        order = ()
        if event is not None:
            lines = [f"{action}{' ' + target if target else ''}: {'accepted' if accepted else 'rejected'} ({event['code']})",
                     f"Turn {event['turn_before']} -> {event['turn_after']}; position {tuple(event['position_before'])} -> {tuple(event['position_after'])}"]
            if event["collected_artifact_id"]: lines.append(f"Collected {event['collected_artifact_id']}; recorded reward +{event['artifact_reward']}.")
            if event["defeated_enemy_id"]: lines.append(f"Engaged {event['defeated_enemy_id']}; recorded penalty +{event['encounter_penalty']}.")
            if kind == PATROL or (kind == PUBLIC_PROJECT and data["admission"]["configuration"]["rules"]["mode"] == "patrol"):
                order = tuple(event["order"])
                lines.append("Recorded order: " + " > ".join(order))
                lines.append(f"Patrol clock {event['patrol_turn_before']} -> {event['patrol_turn_after']}.")
                if event["terminal"]: lines.append("Recorded terminal: " + event["terminal"])
        if terminal: lines.append("Recorded result: " + status + " / " + reason)
        artifacts, enemies = _entities(snapshot, frames[-1] if frames else None)
        frames.append(Frame(i, snapshot.turn, position, action, accepted, target, status, reason, completed,
            direction, pose_for(action, accepted, completed, terminal), artifacts, enemies, tuple(sorted(visited)),
            tuple(lines), order, data["frames"][i].get("patrol_turn")))
    first = snapshots[0]
    metrics = tuple((key, str(summary[key])) for key in ("T", "P", "A", "C", "L", "E", "score") if key in summary)
    metrics += (("B", str(first.base_points)), ("r", str(first.deduction_rate)), ("Q", str(first.zero_score_excess)),
                ("H", str(first.max_turns)), ("D", "none" if first.deadline_turn is None else str(first.deadline_turn)))
    return Recording(title, kind, 2 if kind == PUBLIC_PROJECT else 1, hashlib.sha256(raw).hexdigest(), first.level.terrain.terrain_rows,
        cell(first.level.start), cell(first.level.exit), tuple(frames), metrics, summary["outcome"], summary["code"], True)


def load_public(raw, title="Public practice — DEVELOPMENT"):
    from src.framework.static_records import read_json
    data = read_json(raw)
    if type(data) is dict and data.get("format") == PUBLIC_PROJECT:
        from src.framework.public_project.recording import validate_record
        view = validate_record(raw)
        source = data["source_identity"]["sha256"][:12]
        return recording_from_view(raw, view, data,
            title + " | saved source " + source + " | exact public minimum; no grade", PUBLIC_PROJECT)
    from src.framework.public_practice.records import validate_public_record
    view = validate_public_record(raw)
    data = json.loads(raw)
    source = data["source_identity"]["sha256"][:12]
    return recording_from_view(raw, view, data,
        title + " | saved source " + source + " | analytic L; no grade", PUBLIC)
