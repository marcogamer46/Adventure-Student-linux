"""Trusted patrol provenance and definitions, composing the placement chain."""

from __future__ import annotations

from src.api import LevelDefinition, LevelSpecification, PatrolDefinition, Position
from src.framework.level_entity_placement_validation import (
    LevelEntityPlacementValidationError, validate_level_entity_placement_candidate,
)

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_PROVENANCE", "PLACEMENT_INVALID", "INVALID_LEVEL",
    "PATROLS_NOT_ALLOWED", "INVALID_PATROL", "UNKNOWN_PATROL_ENEMY",
    "DUPLICATE_PATROL_ENEMY", "PATROL_NOT_TRAVERSABLE", "INVALID_PATROL_STEP",
    "PATROL_INITIAL_POSITION_MISMATCH",
})
_PROVENANCES = frozenset({"student-static", "instructor-patrol"})
_Coordinates = tuple[int, int]
_Patrol = tuple[str, tuple[_Coordinates, ...], int]


class LevelPatrolValidationError(ValueError):
    """A read-only finite code without schedule or nested diagnostic text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level patrol validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _capture_patrols(patrols: tuple[PatrolDefinition, ...]) -> tuple[_Patrol, ...]:
    # Prove every entry type before reading any record. Then copy only built-in
    # IDs, coordinates and phases, before looking up any enemy relationship.
    if any(type(patrol) is not PatrolDefinition for patrol in patrols):
        raise LevelPatrolValidationError("INVALID_PATROL")
    records = []
    for patrol in patrols:
        try:
            enemy_id = patrol.enemy_id
            positions = patrol.positions
            phase = patrol.initial_phase
        except AttributeError:
            raise LevelPatrolValidationError("INVALID_PATROL") from None
        if type(enemy_id) is not str or not enemy_id or enemy_id != enemy_id.strip():
            raise LevelPatrolValidationError("INVALID_PATROL")
        if type(positions) is not tuple or not positions:
            raise LevelPatrolValidationError("INVALID_PATROL")
        coordinates = []
        for position in positions:
            if type(position) is not Position:
                raise LevelPatrolValidationError("INVALID_PATROL")
            try:
                row, column = position.row, position.column
            except AttributeError:
                raise LevelPatrolValidationError("INVALID_PATROL") from None
            if type(row) is not int or type(column) is not int:
                raise LevelPatrolValidationError("INVALID_PATROL")
            coordinates.append((row, column))
        if type(phase) is not int or not 0 <= phase < len(positions):
            raise LevelPatrolValidationError("INVALID_PATROL")
        records.append((enemy_id, tuple(coordinates), phase))
    return tuple(records)


def validate_level_patrol_candidate(
    level: LevelDefinition, specification: LevelSpecification, original_seed: int,
    provenance: str,
) -> None:
    """Validate definitions with provenance supplied by a trusted host.

    Order: outer types, provenance, Task 016, collection shape. Student-static
    requires an empty tuple without reading entries. Instructor-patrol captures
    all entry types and complete records, then checks all enemy matches, unique
    schedules, traversability, cyclic steps and initial-phase binding, in that
    order. Future co-locations and endpoint visits are legal. Nothing advances.
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelPatrolValidationError("WRONG_TYPE")
    if type(provenance) is not str or provenance not in _PROVENANCES:
        raise LevelPatrolValidationError("INVALID_PROVENANCE")
    try:
        validate_level_entity_placement_candidate(level, specification, original_seed)
    except LevelEntityPlacementValidationError:
        raise LevelPatrolValidationError("PLACEMENT_INVALID") from None

    try:
        patrols = level.patrols
    except AttributeError:
        raise LevelPatrolValidationError("INVALID_LEVEL") from None
    if type(patrols) is not tuple:
        raise LevelPatrolValidationError("INVALID_LEVEL")
    if provenance == "student-static":
        if patrols:
            raise LevelPatrolValidationError("PATROLS_NOT_ALLOWED")
        return

    records = _capture_patrols(patrols)
    # Task 016 proved exact enemy records, unique IDs and legal initial positions.
    # Their safe coordinates bind the initial phase without Position equality/hash.
    initial_positions = {enemy.enemy_id: (enemy.position.row, enemy.position.column)
                         for enemy in level.enemies}
    if any(enemy_id not in initial_positions for enemy_id, _, _ in records):
        raise LevelPatrolValidationError("UNKNOWN_PATROL_ENEMY")
    scheduled = set()
    for enemy_id, _, _ in records:
        if enemy_id in scheduled:
            raise LevelPatrolValidationError("DUPLICATE_PATROL_ENEMY")
        scheduled.add(enemy_id)

    terrain = level.terrain
    for _, coordinates, _ in records:
        if any(not terrain.is_traversable(Position(row, column)) for row, column in coordinates):
            raise LevelPatrolValidationError("PATROL_NOT_TRAVERSABLE")
    for _, coordinates, _ in records:
        for index, (row, column) in enumerate(coordinates):
            next_row, next_column = coordinates[(index + 1) % len(coordinates)]
            if abs(next_row - row) + abs(next_column - column) > 1:
                raise LevelPatrolValidationError("INVALID_PATROL_STEP")
    for enemy_id, coordinates, phase in records:
        if coordinates[phase] != initial_positions[enemy_id]:
            raise LevelPatrolValidationError("PATROL_INITIAL_POSITION_MISMATCH")
