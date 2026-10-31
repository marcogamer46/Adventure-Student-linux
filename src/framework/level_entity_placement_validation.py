"""Initial entity placement, composing the original numeric/structural chain."""

from __future__ import annotations

from src.api import LevelDefinition, LevelSpecification, Position
from src.framework.level_entity_range_validation import (
    LevelEntityRangeValidationError, validate_level_entity_range_candidate,
)

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "RANGE_INVALID", "INVALID_ARTIFACT",
    "INVALID_ENEMY", "ARTIFACT_NOT_TRAVERSABLE", "ENEMY_NOT_TRAVERSABLE",
    "ENEMY_ON_START", "ENTITY_ON_ENDPOINT", "ENTITY_OVERLAP",
})
_Coordinates = tuple[int, int]


class LevelEntityPlacementValidationError(ValueError):
    """A read-only finite code without coordinates or nested diagnostic text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level entity placement validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _capture_positions(entities: tuple, code: str) -> tuple[_Coordinates, ...]:
    # Task 015 proved exact tuples and canonical entity types. Copy only safe
    # integer coordinates; relationships never invoke Position equality/hash.
    coordinates = []
    for entity in entities:
        try:
            position = entity.position
        except AttributeError:
            raise LevelEntityPlacementValidationError(code) from None
        if type(position) is not Position:
            raise LevelEntityPlacementValidationError(code)
        try:
            row, column = position.row, position.column
        except AttributeError:
            raise LevelEntityPlacementValidationError(code) from None
        if type(row) is not int or type(column) is not int:
            raise LevelEntityPlacementValidationError(code)
        coordinates.append((row, column))
    return tuple(coordinates)


def _is_traversable(position: _Coordinates, rows: tuple[str, ...]) -> bool:
    # The terrain rows passed Tasks 010–015. Bounds precede indexing, including
    # negative/large canonical probe coordinates; no graph is rebuilt here.
    row, column = position
    return (0 <= row < len(rows) and 0 <= column < len(rows[0])
            and rows[row][column] == ".")


def validate_level_entity_placement_candidate(
    level: LevelDefinition, specification: LevelSpecification, original_seed: int,
) -> None:
    """Check initial floor/endpoint/overlap rules after unchanged Tasks 015–010.

    Check order: outer types, exact placement bools, Task 015, all artifact then
    enemy position shapes, artifact then enemy traversability, enemy on start,
    endpoint permission, overlap. Negative integer coordinates are well-shaped
    but outside the board. Every position is captured before relationships.
    Patrols, gameplay feasibility, scoring and generation remain separate.
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelEntityPlacementValidationError("WRONG_TYPE")
    try:
        overlap_allowed = specification.allow_entity_overlap
        endpoints_allowed = specification.allow_entities_on_endpoints
    except AttributeError:
        raise LevelEntityPlacementValidationError("INVALID_SPECIFICATION") from None
    if type(overlap_allowed) is not bool or type(endpoints_allowed) is not bool:
        raise LevelEntityPlacementValidationError("INVALID_SPECIFICATION")

    try:
        validate_level_entity_range_candidate(level, specification, original_seed)
    except LevelEntityRangeValidationError:
        raise LevelEntityPlacementValidationError("RANGE_INVALID") from None

    artifact_positions = _capture_positions(level.artifacts, "INVALID_ARTIFACT")
    enemy_positions = _capture_positions(level.enemies, "INVALID_ENEMY")
    rows = level.terrain.terrain_rows
    if any(not _is_traversable(position, rows) for position in artifact_positions):
        raise LevelEntityPlacementValidationError("ARTIFACT_NOT_TRAVERSABLE")
    if any(not _is_traversable(position, rows) for position in enemy_positions):
        raise LevelEntityPlacementValidationError("ENEMY_NOT_TRAVERSABLE")

    # Task 011 already proved both endpoints are canonical integer Positions.
    start = (level.start.row, level.start.column)
    exit_position = (level.exit.row, level.exit.column)
    if start in enemy_positions:
        raise LevelEntityPlacementValidationError("ENEMY_ON_START")
    positions = artifact_positions + enemy_positions
    if not endpoints_allowed and any(position == start or position == exit_position
                                     for position in positions):
        raise LevelEntityPlacementValidationError("ENTITY_ON_ENDPOINT")
    if not overlap_allowed:
        occupied = set()
        for position in positions:
            if position in occupied:
                raise LevelEntityPlacementValidationError("ENTITY_OVERLAP")
            occupied.add(position)
