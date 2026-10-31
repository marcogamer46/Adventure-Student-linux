"""Exact instructor-patrol no-collection transition model; no callbacks."""
from src.api import LevelDefinition, Position, WorldAction, WorldActionType
from src.framework.generation import canonical
from src.framework.level_patrol_validation import validate_level_patrol_candidate

MOVES = ((WorldActionType.MOVE_NORTH, -1, 0), (WorldActionType.MOVE_SOUTH, 1, 0),
         (WorldActionType.MOVE_WEST, 0, -1), (WorldActionType.MOVE_EAST, 0, 1))


def capture_inputs(level, specification, seed):
    request = canonical.level_request(specification, seed)
    specification, seed = canonical.read_level_request(request)
    if type(level) is not LevelDefinition:
        raise canonical.CanonicalError("INVALID_LEVEL")
    validate_level_patrol_candidate(level, specification, seed, provenance="instructor-patrol")
    record = canonical.level_record(level)
    owned = canonical.read_level(record)
    validate_level_patrol_candidate(owned, specification, seed, provenance="instructor-patrol")
    return owned, specification, canonical.canonical_bytes(record), canonical.canonical_bytes(request)


def initial_state(level):
    return level.start.row, level.start.column, 0, 0


def patrol_positions(level, turns):
    return {(p.positions[(p.initial_phase + turns) % p.period].row,
             p.positions[(p.initial_phase + turns) % p.period].column) for p in level.patrols}


def state_valid(level, state, max_turns, rules):
    row, column, defeated, turns = state
    patrol_ids = {p.enemy_id for p in level.patrols}
    static_mask = sum(1 << i for i, e in enumerate(level.enemies) if e.enemy_id not in patrol_ids)
    return (not defeated & ~static_mask and 0 <= turns < max_turns
        and (rules.deadline_turn is None or turns < rules.deadline_turn)
        and level.terrain.is_traversable(Position(row, column))
        and (row, column) not in patrol_positions(level, turns)
        and not any(e.enemy_id not in patrol_ids and not defeated & (1 << i)
                    and (row, column) == (e.position.row, e.position.column) for i, e in enumerate(level.enemies)))


def successors(level, state, max_turns, rules):
    """Only continuing or completed transitions enter certification evidence."""
    row, column, defeated, turns = state
    if not state_valid(level, state, max_turns, rules):
        return
    patrol_ids = {p.enemy_id for p in level.patrols}
    occupied = patrol_positions(level, turns) | {
        (e.position.row, e.position.column) for i, e in enumerate(level.enemies)
        if e.enemy_id not in patrol_ids and not defeated & (1 << i)}
    options = []
    for kind, dr, dc in MOVES:
        next_position = (row + dr, column + dc)
        if level.terrain.is_traversable(Position(*next_position)) and next_position not in occupied:
            options.append(((*next_position, defeated, turns + 1), WorldAction(kind), 1, False))
    if rules.allow_engage:
        for i, e in enumerate(level.enemies):
            if (e.enemy_id not in patrol_ids and not defeated & (1 << i)
                    and abs(row - e.position.row) + abs(column - e.position.column) == 1):
                options.append(((row, column, defeated | (1 << i), turns + 1),
                                WorldAction(WorldActionType.ENGAGE, target_id=e.enemy_id), 1 + e.encounter_penalty, False))
    if rules.allow_wait:
        options.append(((row, column, defeated, turns + 1), WorldAction.wait(), 1, False))
    # EXIT increments T and terminates before any future phase, collision or limit.
    if (row, column) == (level.exit.row, level.exit.column):
        yield (row, column, defeated, turns + 1), WorldAction(WorldActionType.EXIT), 1, True
    for next_state, action, cost, _ in options:
        # A non-EXIT phase advance happens before collision, deadline and H.
        if state_valid(level, next_state, max_turns, rules):
            yield next_state, action, cost, False
