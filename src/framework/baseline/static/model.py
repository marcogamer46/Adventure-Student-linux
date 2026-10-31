"""Declared static action model and reuse of the original validator chain."""
from src.api import LevelDefinition, Position, WorldAction, WorldActionType
from src.framework.generation import canonical
from src.framework.level_patrol_validation import validate_level_patrol_candidate

MOVES = (
    (WorldActionType.MOVE_NORTH, -1, 0), (WorldActionType.MOVE_SOUTH, 1, 0),
    (WorldActionType.MOVE_WEST, 0, -1), (WorldActionType.MOVE_EAST, 0, 1),
)


def capture_inputs(level, specification, seed, validator=validate_level_patrol_candidate):
    """Retain inputs before inspecting candidate content, then validate copies."""
    request = canonical.level_request(specification, seed)
    specification, seed = canonical.read_level_request(request)
    if type(level) is not LevelDefinition:
        raise canonical.CanonicalError("INVALID_LEVEL")
    validator(level, specification, seed, provenance="student-static")
    record = canonical.level_record(level)
    owned = canonical.read_level(record)
    validator(owned, specification, seed, provenance="student-static")
    return owned, specification, canonical.canonical_bytes(record), canonical.canonical_bytes(request)


def initial_state(level):
    return (level.start.row, level.start.column, 0, 0)


def successors(level, state, max_turns, allow_wait):
    """Yield (next state, action, cost, completion); COLLECT is excluded."""
    row, column, defeated, turns = state
    if turns >= max_turns:
        return
    occupied = {(enemy.position.row, enemy.position.column) for index, enemy in enumerate(level.enemies)
                if not defeated & (1 << index)}
    for kind, dr, dc in MOVES:
        position = Position(row + dr, column + dc)
        if level.terrain.is_traversable(position) and (position.row, position.column) not in occupied:
            yield ((position.row, position.column, defeated, turns + 1), WorldAction(kind), 1, False)
    for index, enemy in enumerate(level.enemies):
        if (not defeated & (1 << index)
                and abs(row - enemy.position.row) + abs(column - enemy.position.column) == 1):
            action = WorldAction(WorldActionType.ENGAGE, target_id=enemy.enemy_id)
            yield ((row, column, defeated | (1 << index), turns + 1), action, 1 + enemy.encounter_penalty, False)
    if allow_wait:
        yield ((row, column, defeated, turns + 1), WorldAction.wait(), 1, False)
    if (row, column) == (level.exit.row, level.exit.column):
        yield ((row, column, defeated, turns + 1), WorldAction(WorldActionType.EXIT), 1, True)
