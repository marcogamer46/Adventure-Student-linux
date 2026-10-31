"""Instructor-only structural validation of one supplied terrain candidate.

No generator execution, level admission, certification or runtime wiring.
"""

from __future__ import annotations

from src.api import Terrain, TerrainGenerationSpec, TerrainTopology

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "INVALID_TERRAIN",
    "DIMENSION_MISMATCH", "OPEN_COUNT_OUT_OF_RANGE", "DISCONNECTED",
    "TOPOLOGY_MISMATCH",
})
_ORTHOGONAL_DELTAS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class TerrainValidationError(ValueError):
    """A fixed, bounded code; no candidate data or exception text is retained."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown terrain validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def validate_terrain_candidate(
    terrain: Terrain, specification: TerrainGenerationSpec,
) -> None:
    """Return None on conformance, otherwise raise TerrainValidationError.

    Checks run in order: canonical types, specification/terrain local shape,
    dimensions, open count, connectivity, topology. Runtime is O(rows*columns)
    with O(open tiles) graph storage. max_attempts is not a retry instruction.
    """
    if type(terrain) is not Terrain or type(specification) is not TerrainGenerationSpec:
        raise TerrainValidationError("WRONG_TYPE")

    # Canonical class identity alone is not enough: slots may have been corrupted
    # or construction bypassed. Recheck captured fields through owned constructors
    # before graph operations. Exact primitive checks prevent foreign hooks.
    try:
        spec = TerrainGenerationSpec(
            rows=specification.rows, columns=specification.columns,
            min_open_tiles=specification.min_open_tiles,
            max_open_tiles=specification.max_open_tiles,
            max_attempts=specification.max_attempts, topology=specification.topology,
        )
    except (AttributeError, TypeError, ValueError):
        raise TerrainValidationError("INVALID_SPECIFICATION") from None
    try:
        candidate = Terrain(terrain.terrain_rows)
    except (AttributeError, TypeError, ValueError):
        raise TerrainValidationError("INVALID_TERRAIN") from None

    if candidate.rows != spec.rows or candidate.columns != spec.columns:
        raise TerrainValidationError("DIMENSION_MISMATCH")
    open_tiles = {
        (row, column)
        for row, symbols in enumerate(candidate.terrain_rows)
        for column, symbol in enumerate(symbols)
        if symbol == "."
    }
    count = len(open_tiles)
    if not spec.min_open_tiles <= count <= spec.max_open_tiles:
        raise TerrainValidationError("OPEN_COUNT_OUT_OF_RANGE")
    if not open_tiles:
        if spec.topology is TerrainTopology.GENERAL:
            return
        raise TerrainValidationError("TOPOLOGY_MISMATCH")

    origin = min(open_tiles)
    visited = {origin}
    pending = [origin]
    degrees = {}
    while pending:
        row, column = pending.pop()
        degree = 0
        for dr, dc in _ORTHOGONAL_DELTAS:
            neighbor = (row + dr, column + dc)
            if neighbor in open_tiles:
                degree += 1
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        degrees[(row, column)] = degree
    if len(visited) != count:
        raise TerrainValidationError("DISCONNECTED")
    if spec.topology is TerrainTopology.GENERAL:
        return

    if spec.topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH):
        simple_path = (
            count >= 2
            and sum(degree == 1 for degree in degrees.values()) == 2
            and all(degree in (1, 2) for degree in degrees.values())
        )
        on_one_axis = (
            all(row == origin[0] for row, _ in open_tiles)
            or all(column == origin[1] for _, column in open_tiles)
        )
        matches_axis = on_one_axis if spec.topology is TerrainTopology.STRAIGHT_PATH else not on_one_axis
        if simple_path and matches_axis:
            return
    elif spec.topology is TerrainTopology.BRANCHING_TREE:
        # Connectivity was established above; for a finite undirected graph,
        # |E| = |V| - 1 then proves acyclicity. Each edge contributes two degrees.
        edge_count = sum(degrees.values()) // 2
        if edge_count == count - 1 and any(degree >= 3 for degree in degrees.values()):
            return
    raise TerrainValidationError("TOPOLOGY_MISMATCH")
