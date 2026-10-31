"""Canonical immutable v1 values; no runtime or student dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


def _integer(value: object, name: str, minimum: int | None = None) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, not bool or a coerced value.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} is below its minimum.")


def _identity(value: object, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty and already trimmed.")


def _exact(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise TypeError(f"{name} must be a canonical {expected.__name__}.")


@dataclass(frozen=True, slots=True, order=True)
class Position:
    row: int
    column: int

    def __post_init__(self) -> None:
        _integer(self.row, "row")
        _integer(self.column, "column")

    def manhattan_distance(self, other: Position) -> int:
        _exact(other, Position, "other")
        return abs(self.row - other.row) + abs(self.column - other.column)


@dataclass(frozen=True, slots=True)
class Terrain:
    terrain_rows: tuple[str, ...]

    def __post_init__(self) -> None:
        _exact(self.terrain_rows, tuple, "terrain_rows")
        if not self.terrain_rows:
            raise ValueError("Terrain must contain rows.")
        if any(type(row) is not str or not row for row in self.terrain_rows):
            raise ValueError("Terrain rows must be nonempty strings.")
        width = len(self.terrain_rows[0])
        if any(len(row) != width or set(row) - {"#", "."} for row in self.terrain_rows):
            raise ValueError("Terrain must be rectangular and contain only # and .")

    @property
    def rows(self) -> int:
        return len(self.terrain_rows)

    @property
    def columns(self) -> int:
        return len(self.terrain_rows[0])

    def is_in_bounds(self, position: Position) -> bool:
        _exact(position, Position, "position")
        return 0 <= position.row < self.rows and 0 <= position.column < self.columns

    def is_traversable(self, position: Position) -> bool:
        return self.is_in_bounds(position) and self.terrain_rows[position.row][position.column] == "."


@dataclass(frozen=True, slots=True)
class CharacterDefinition:
    agent_id: str

    def __post_init__(self) -> None:
        _identity(self.agent_id, "agent_id")


@dataclass(frozen=True, slots=True)
class ArtifactDefinition:
    """Initial data only; constructing it does not enable artifact gameplay."""

    artifact_id: str
    position: Position
    value: int

    def __post_init__(self) -> None:
        _identity(self.artifact_id, "artifact_id")
        _exact(self.position, Position, "position")
        _integer(self.value, "value", 0)
        object.__setattr__(self, "position", Position(self.position.row, self.position.column))


@dataclass(frozen=True, slots=True)
class EnemyDefinition:
    """Initial data only; patrol schedules are separate instructor values."""

    enemy_id: str
    position: Position
    encounter_penalty: int

    def __post_init__(self) -> None:
        _identity(self.enemy_id, "enemy_id")
        _exact(self.position, Position, "position")
        _integer(self.encounter_penalty, "encounter_penalty", 0)
        object.__setattr__(self, "position", Position(self.position.row, self.position.column))


class TerrainTopology(str, Enum):
    GENERAL = "GENERAL"
    STRAIGHT_PATH = "STRAIGHT_PATH"
    BENT_PATH = "BENT_PATH"
    BRANCHING_TREE = "BRANCHING_TREE"


@dataclass(frozen=True, slots=True, kw_only=True)
class TerrainGenerationSpec:
    rows: int
    columns: int
    min_open_tiles: int
    max_open_tiles: int
    max_attempts: int
    topology: TerrainTopology = TerrainTopology.GENERAL

    def __post_init__(self) -> None:
        for name in ("rows", "columns", "max_attempts"):
            _integer(getattr(self, name), name, 1)
        for name in ("min_open_tiles", "max_open_tiles"):
            _integer(getattr(self, name), name, 0)
        _exact(self.topology, TerrainTopology, "topology")
        if not self.min_open_tiles <= self.max_open_tiles <= self.rows * self.columns:
            raise ValueError("Open-tile bounds must be ordered and fit the board area.")
        # Graph shape and feasibility belong to future original-spec admission.


@dataclass(frozen=True, slots=True, kw_only=True)
class LevelSpecification:
    level_id: str
    profile_id: str
    agent_id: str
    terrain_spec: TerrainGenerationSpec
    artifact_count: int
    enemy_count: int
    artifact_value_min: int
    artifact_value_max: int
    enemy_penalty_min: int
    enemy_penalty_max: int
    min_route_moves: int
    max_route_moves: int
    min_branch_tiles: int
    max_dead_end_tiles: int
    require_alternate_path: bool
    allow_entity_overlap: bool
    allow_entities_on_endpoints: bool
    max_turns: int
    max_attempts: int

    def __post_init__(self) -> None:
        for name in ("level_id", "profile_id", "agent_id"):
            _identity(getattr(self, name), name)
        _exact(self.terrain_spec, TerrainGenerationSpec, "terrain_spec")
        for name in (
            "artifact_count", "enemy_count", "artifact_value_min", "artifact_value_max",
            "enemy_penalty_min", "enemy_penalty_max", "min_route_moves", "max_route_moves",
            "min_branch_tiles", "max_dead_end_tiles",
        ):
            _integer(getattr(self, name), name, 0)
        for lower, upper in (
            ("artifact_value_min", "artifact_value_max"),
            ("enemy_penalty_min", "enemy_penalty_max"),
            ("min_route_moves", "max_route_moves"),
        ):
            if getattr(self, lower) > getattr(self, upper):
                raise ValueError(f"{lower} must not exceed {upper}.")
        for name in ("require_alternate_path", "allow_entity_overlap", "allow_entities_on_endpoints"):
            _exact(getattr(self, name), bool, name)
        for name in ("max_turns", "max_attempts"):
            _integer(getattr(self, name), name, 1)
        spec = self.terrain_spec
        object.__setattr__(self, "terrain_spec", TerrainGenerationSpec(
            rows=spec.rows, columns=spec.columns, min_open_tiles=spec.min_open_tiles,
            max_open_tiles=spec.max_open_tiles, max_attempts=spec.max_attempts,
            topology=spec.topology,
        ))


@dataclass(frozen=True, slots=True, kw_only=True)
class PatrolDefinition:
    enemy_id: str
    positions: tuple[Position, ...]
    initial_phase: int = 0

    def __post_init__(self) -> None:
        _identity(self.enemy_id, "enemy_id")
        _exact(self.positions, tuple, "positions")
        if not self.positions:
            raise ValueError("A patrol must contain at least one position.")
        for position in self.positions:
            _exact(position, Position, "position")
        _integer(self.initial_phase, "initial_phase", 0)
        if self.initial_phase >= len(self.positions):
            raise ValueError("initial_phase must be within the patrol period.")
        object.__setattr__(self, "positions", tuple(
            Position(position.row, position.column) for position in self.positions
        ))

    @property
    def period(self) -> int:
        return len(self.positions)


@dataclass(frozen=True, slots=True, kw_only=True)
class EnemyObservation:
    enemy_id: str
    position: Position | None
    phase: int | None

    def __post_init__(self) -> None:
        _identity(self.enemy_id, "enemy_id")
        if self.position is not None:
            _exact(self.position, Position, "position")
            object.__setattr__(self, "position", Position(self.position.row, self.position.column))
        if self.phase is not None:
            _integer(self.phase, "phase", 0)
        # Static/removal/patrol consistency requires the complete admitted world.


class WorldActionType(str, Enum):
    MOVE_NORTH = "MOVE_NORTH"
    MOVE_SOUTH = "MOVE_SOUTH"
    MOVE_WEST = "MOVE_WEST"
    MOVE_EAST = "MOVE_EAST"
    COLLECT = "COLLECT"
    INTERACT = "INTERACT"
    ENGAGE = "ENGAGE"
    WAIT = "WAIT"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class WorldAction:
    action_type: WorldActionType
    target_id: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        _exact(self.action_type, WorldActionType, "action_type")
        if self.target_id is not None:
            _identity(self.target_id, "target_id")

    @classmethod
    def wait(cls) -> WorldAction:
        return cls(WorldActionType.WAIT)


@dataclass(frozen=True, slots=True, kw_only=True)
class LevelDefinition:
    level_id: str
    profile_id: str
    seed: int
    terrain: Terrain
    start: Position
    exit: Position
    character: CharacterDefinition
    artifacts: tuple[ArtifactDefinition, ...] = ()
    enemies: tuple[EnemyDefinition, ...] = ()
    patrols: tuple[PatrolDefinition, ...] = ()

    def __post_init__(self) -> None:
        for name in ("level_id", "profile_id"):
            _identity(getattr(self, name), name)
        _integer(self.seed, "seed", 0)
        _exact(self.terrain, Terrain, "terrain")
        _exact(self.start, Position, "start")
        _exact(self.exit, Position, "exit")
        _exact(self.character, CharacterDefinition, "character")
        _exact(self.artifacts, tuple, "artifacts")
        _exact(self.enemies, tuple, "enemies")
        _exact(self.patrols, tuple, "patrols")
        for entity in self.artifacts:
            _exact(entity, ArtifactDefinition, "artifact")
        for entity in self.enemies:
            _exact(entity, EnemyDefinition, "enemy")
        for patrol in self.patrols:
            _exact(patrol, PatrolDefinition, "patrol")
        # Relationships and certified policy are checked by the host referee.
        object.__setattr__(self, "terrain", Terrain(self.terrain.terrain_rows))
        object.__setattr__(self, "start", Position(self.start.row, self.start.column))
        object.__setattr__(self, "exit", Position(self.exit.row, self.exit.column))
        object.__setattr__(self, "character", CharacterDefinition(self.character.agent_id))
        object.__setattr__(self, "artifacts", tuple(sorted((
            ArtifactDefinition(x.artifact_id, Position(x.position.row, x.position.column), x.value)
            for x in self.artifacts
        ), key=lambda entity: entity.artifact_id)))
        object.__setattr__(self, "enemies", tuple(sorted((
            EnemyDefinition(x.enemy_id, Position(x.position.row, x.position.column), x.encounter_penalty)
            for x in self.enemies
        ), key=lambda entity: entity.enemy_id)))
        object.__setattr__(self, "patrols", tuple(sorted((
            PatrolDefinition(enemy_id=x.enemy_id, positions=x.positions, initial_phase=x.initial_phase)
            for x in self.patrols
        ), key=lambda patrol: patrol.enemy_id)))


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldSnapshot:
    level: LevelDefinition
    agent_position: Position
    turn: int
    collected_artifact_ids: tuple[str, ...]
    defeated_enemy_ids: tuple[str, ...]
    base_points: int
    deduction_rate: int
    baseline_cost: int
    zero_score_excess: int
    max_turns: int
    deadline_turn: int | None = None
    allowed_actions: tuple[WorldActionType, ...] = (
        WorldActionType.MOVE_NORTH, WorldActionType.MOVE_SOUTH,
        WorldActionType.MOVE_WEST, WorldActionType.MOVE_EAST,
        WorldActionType.WAIT, WorldActionType.EXIT,
    )
    enemy_observations: tuple[EnemyObservation, ...] = ()

    def __post_init__(self) -> None:
        _exact(self.level, LevelDefinition, "level")
        _exact(self.agent_position, Position, "agent_position")
        for name in ("turn", "base_points", "deduction_rate"):
            _integer(getattr(self, name), name, 0)
        for name in ("baseline_cost", "zero_score_excess", "max_turns"):
            _integer(getattr(self, name), name, 1)
        if self.deadline_turn is not None:
            _integer(self.deadline_turn, "deadline_turn", 1)
        for name in ("collected_artifact_ids", "defeated_enemy_ids"):
            values = getattr(self, name)
            _exact(values, tuple, name)
            for value in values:
                _identity(value, name)
            # Ordering is local; duplicates/subsets remain host relationship checks.
            object.__setattr__(self, name, tuple(sorted(values)))
        _exact(self.allowed_actions, tuple, "allowed_actions")
        for action in self.allowed_actions:
            _exact(action, WorldActionType, "allowed_action")
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("allowed_actions must not contain duplicates.")
        object.__setattr__(self, "allowed_actions", tuple(
            action for action in WorldActionType if action in self.allowed_actions
        ))
        _exact(self.enemy_observations, tuple, "enemy_observations")
        for observation in self.enemy_observations:
            _exact(observation, EnemyObservation, "enemy_observation")
        object.__setattr__(self, "enemy_observations", tuple(sorted((
            EnemyObservation(enemy_id=x.enemy_id, position=x.position, phase=x.phase)
            for x in self.enemy_observations
        ), key=lambda observation: observation.enemy_id)))

    @property
    def level_id(self) -> str:
        return self.level.level_id

    @property
    def seed(self) -> int:
        return self.level.seed

    @property
    def agent_id(self) -> str:
        return self.level.character.agent_id

    @property
    def terrain(self) -> Terrain:
        return self.level.terrain

    @property
    def rows(self) -> int:
        return self.terrain.rows

    @property
    def columns(self) -> int:
        return self.terrain.columns

    @property
    def start_position(self) -> Position:
        return self.level.start

    @property
    def exit_position(self) -> Position:
        return self.level.exit

    def is_in_bounds(self, position: Position) -> bool:
        return self.terrain.is_in_bounds(position)

    def is_traversable(self, position: Position) -> bool:
        return self.terrain.is_traversable(position)


class ContractViolation(Exception):
    def __init__(self, component: str, field: str, reason: str) -> None:
        for value in (component, field, reason):
            if type(value) is not str:
                raise TypeError("ContractViolation diagnostic fields must be strings.")
        self._component = component
        self._field = field
        self._reason = reason
        super().__init__(f"{component}.{field}: {reason}")

    @property
    def component(self) -> str:
        return self._component

    @property
    def field(self) -> str:
        return self._field

    @property
    def reason(self) -> str:
        return self._reason


class GenerationFailure(Exception):
    def __init__(self, component: str, reason: str) -> None:
        for value in (component, reason):
            if type(value) is not str:
                raise TypeError("GenerationFailure diagnostic fields must be strings.")
        self._component = component
        self._reason = reason
        super().__init__(f"{component}: {reason}")

    @property
    def component(self) -> str:
        return self._component

    @property
    def reason(self) -> str:
        return self._reason
