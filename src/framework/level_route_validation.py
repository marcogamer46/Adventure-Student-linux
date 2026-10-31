"""Instructor-only endpoint and terrain-route checks, not full admission."""

from __future__ import annotations

from collections import deque

from src.api import LevelDefinition, LevelSpecification, Position, TerrainTopology
from src.framework.terrain_validation import TerrainValidationError, validate_terrain_candidate

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "INVALID_LEVEL", "TERRAIN_INVALID",
    "ENDPOINTS_NOT_DISTINCT", "ENDPOINT_NOT_TRAVERSABLE", "PATH_ENDPOINT_MISMATCH",
    "ROUTE_DISTANCE_OUT_OF_RANGE", "NO_ROUTE",
})
_ORTHOGONAL_DELTAS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class LevelRouteValidationError(ValueError):
    """A read-only finite code with no candidate data in its message."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level route validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _coordinates(position: Position) -> tuple[int, int]:
    if type(position) is not Position:
        raise LevelRouteValidationError("INVALID_LEVEL")
    try:
        row, column = position.row, position.column
    except AttributeError:
        raise LevelRouteValidationError("INVALID_LEVEL") from None
    if type(row) is not int or type(column) is not int:
        raise LevelRouteValidationError("INVALID_LEVEL")
    return row, column


def validate_level_route_candidate(
    level: LevelDefinition, specification: LevelSpecification,
) -> None:
    """Check terrain, endpoints and inclusive shortest movement-edge bounds.

    Only route-relevant fields are read. Entities, identity, H, retries and
    remaining LevelSpecification relationships are deliberately deferred.
    EXIT is not a movement edge; this distance does not certify baseline L.
    Time is O(rows*columns), auxiliary space O(open tiles).
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelRouteValidationError("WRONG_TYPE")
    try:
        terrain_spec = specification.terrain_spec
        minimum, maximum = specification.min_route_moves, specification.max_route_moves
    except AttributeError:
        raise LevelRouteValidationError("INVALID_SPECIFICATION") from None
    if (type(minimum) is not int or type(maximum) is not int
            or not 0 <= minimum <= maximum):
        raise LevelRouteValidationError("INVALID_SPECIFICATION")
    try:
        terrain = level.terrain
    except AttributeError:
        raise LevelRouteValidationError("INVALID_LEVEL") from None

    # Task 010 owns local terrain/spec shape, dimensions, counts, connectivity
    # and topology. Complete that boundary before touching any endpoint.
    try:
        validate_terrain_candidate(terrain, terrain_spec)
    except TerrainValidationError:
        raise LevelRouteValidationError("TERRAIN_INVALID") from None

    try:
        start, exit_position = level.start, level.exit
    except AttributeError:
        raise LevelRouteValidationError("INVALID_LEVEL") from None
    start_coordinates = _coordinates(start)
    exit_coordinates = _coordinates(exit_position)
    if start_coordinates == exit_coordinates:
        raise LevelRouteValidationError("ENDPOINTS_NOT_DISTINCT")

    # These rows and topology have passed the composed canonical boundary.
    # Tuple coordinates avoid calling endpoint equality or spatial hooks.
    open_tiles = {
        (row, column)
        for row, symbols in enumerate(terrain.terrain_rows)
        for column, symbol in enumerate(symbols)
        if symbol == "."
    }
    if start_coordinates not in open_tiles or exit_coordinates not in open_tiles:
        raise LevelRouteValidationError("ENDPOINT_NOT_TRAVERSABLE")

    if terrain_spec.topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH):
        # Task 010 already proved exactly two leaves. Two distinct selected
        # degree-one vertices therefore are precisely the path's two ends.
        for row, column in (start_coordinates, exit_coordinates):
            degree = sum((row + dr, column + dc) in open_tiles for dr, dc in _ORTHOGONAL_DELTAS)
            if degree != 1:
                raise LevelRouteValidationError("PATH_ENDPOINT_MISMATCH")

    distances = {start_coordinates: 0}
    frontier = deque([start_coordinates])
    while frontier:
        current = frontier.popleft()
        distance = distances[current]
        if current == exit_coordinates:
            if not minimum <= distance <= maximum:
                raise LevelRouteValidationError("ROUTE_DISTANCE_OUT_OF_RANGE")
            return
        row, column = current
        for dr, dc in _ORTHOGONAL_DELTAS:
            neighbor = (row + dr, column + dc)
            if neighbor in open_tiles and neighbor not in distances:
                distances[neighbor] = distance + 1
                frontier.append(neighbor)
    # Defensive only: composed connectivity and valid endpoints imply a route.
    raise LevelRouteValidationError("NO_ROUTE")
