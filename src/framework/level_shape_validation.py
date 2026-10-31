"""Instructor graph-shape validation, composing the terrain/route boundaries."""

from __future__ import annotations

from src.api import LevelDefinition, LevelSpecification, TerrainGenerationSpec, TerrainTopology
from src.framework.level_route_validation import LevelRouteValidationError, validate_level_route_candidate

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "ROUTE_INVALID",
    "BRANCH_COUNT_BELOW_MINIMUM", "DEAD_END_COUNT_ABOVE_MAXIMUM", "ALTERNATE_PATH_REQUIRED",
})
_ORTHOGONAL_DELTAS = ((-1, 0), (1, 0), (0, -1), (0, 1))
_Vertex = tuple[int, int]
_Graph = dict[_Vertex, tuple[_Vertex, ...]]


class LevelShapeValidationError(ValueError):
    """A read-only finite code; messages contain no candidate or nested text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level shape validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _adjacency(rows: tuple[str, ...]) -> _Graph:
    vertices = {(row, column) for row, symbols in enumerate(rows)
                for column, symbol in enumerate(symbols) if symbol == "."}
    return {
        (row, column): tuple((row + dr, column + dc) for dr, dc in _ORTHOGONAL_DELTAS
                             if (row + dr, column + dc) in vertices)
        for row, column in vertices
    }


def _degree_counts(graph: _Graph) -> tuple[int, int]:
    """Count all vertices, including endpoints; degree zero is not a dead end."""
    return (sum(len(neighbors) >= 3 for neighbors in graph.values()),
            sum(len(neighbors) == 1 for neighbors in graph.values()))


def _has_alternate_path(graph: _Graph, start: _Vertex, exit_position: _Vertex) -> bool:
    """Analyze a connected graph in O(V+E), without enumerating simple paths."""
    discovery = {start: 0}
    low = {start: 0}
    parents = {start: None}
    bridges = set()
    # A suspended neighbor iterator is the explicit DFS call frame. Fixed
    # neighbor order plus the supplied start makes traversal deterministic.
    pending = [(start, iter(graph[start]))]
    while pending:
        vertex, neighbors = pending[-1]
        neighbor = next(neighbors, None)
        if neighbor is not None:
            if neighbor == parents[vertex]:
                continue
            if neighbor in discovery:
                low[vertex] = min(low[vertex], discovery[neighbor])
            else:
                parents[neighbor] = vertex
                discovery[neighbor] = low[neighbor] = len(discovery)
                pending.append((neighbor, iter(graph[neighbor])))
        else:
            pending.pop()
            parent = parents[vertex]
            if parent is not None:
                if low[vertex] > discovery[parent]:
                    bridges.add((parent, vertex))
                low[parent] = min(low[parent], low[vertex])

    # The DFS parent chain is one simple start-to-exit path. It is unique iff
    # every edge on it is a bridge. Removing any non-bridge leaves the endpoints
    # connected and supplies a different simple path. Off-path cycles do not
    # help; bridges elsewhere on this path do not prohibit alternatives.
    vertex = exit_position
    while vertex != start:
        parent = parents[vertex]
        if (parent, vertex) not in bridges:
            return True
        vertex = parent
    return False


def validate_level_shape_candidate(
    level: LevelDefinition, specification: LevelSpecification,
) -> None:
    """Validate one candidate's complete terrain/route/graph-shape constraints.

    Topology-derived contradictions are instructor configuration failures,
    checked before candidate conformance. No general feasibility solver is run.
    Identity/entities, H, generation, certification and runtime remain deferred.
    Time is O(rows*columns), auxiliary storage O(open tiles).
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelShapeValidationError("WRONG_TYPE")
    try:
        minimum_branches = specification.min_branch_tiles
        maximum_dead_ends = specification.max_dead_end_tiles
        alternate_required = specification.require_alternate_path
        terrain_spec = specification.terrain_spec
    except AttributeError:
        raise LevelShapeValidationError("INVALID_SPECIFICATION") from None
    if (type(minimum_branches) is not int or minimum_branches < 0
            or type(maximum_dead_ends) is not int or maximum_dead_ends < 0
            or type(alternate_required) is not bool
            or type(terrain_spec) is not TerrainGenerationSpec):
        raise LevelShapeValidationError("INVALID_SPECIFICATION")
    try:
        topology = terrain_spec.topology
    except AttributeError:
        raise LevelShapeValidationError("INVALID_SPECIFICATION") from None
    if type(topology) is not TerrainTopology:
        raise LevelShapeValidationError("INVALID_SPECIFICATION")
    if topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH):
        if minimum_branches > 0 or maximum_dead_ends < 2 or alternate_required:
            raise LevelShapeValidationError("INVALID_SPECIFICATION")
    elif topology is TerrainTopology.BRANCHING_TREE:
        if maximum_dead_ends < 3 or alternate_required:
            raise LevelShapeValidationError("INVALID_SPECIFICATION")

    # Task 011 composes Task 010. Do not duplicate either primitive's checks.
    try:
        validate_level_route_candidate(level, specification)
    except LevelRouteValidationError:
        raise LevelShapeValidationError("ROUTE_INVALID") from None

    graph = _adjacency(level.terrain.terrain_rows)
    branches, dead_ends = _degree_counts(graph)
    if branches < minimum_branches:
        raise LevelShapeValidationError("BRANCH_COUNT_BELOW_MINIMUM")
    if dead_ends > maximum_dead_ends:
        raise LevelShapeValidationError("DEAD_END_COUNT_ABOVE_MAXIMUM")
    if alternate_required:
        start = (level.start.row, level.start.column)
        exit_position = (level.exit.row, level.exit.column)
        if not _has_alternate_path(graph, start, exit_position):
            raise LevelShapeValidationError("ALTERNATE_PATH_REQUIRED")
