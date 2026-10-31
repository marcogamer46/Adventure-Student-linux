"""Detached presentation values. No actions, simulation or scoring operations."""
from dataclasses import dataclass

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: str
    position: Cell
    value: int
    patrol: bool = False
    phase: int | None = None
    direction: str = "south"


@dataclass(frozen=True, slots=True)
class Frame:
    index: int
    turn: int
    position: Cell
    action: str
    accepted: bool | None
    target: str | None
    status: str
    reason: str
    completed: bool
    direction: str
    pose: str
    artifacts: tuple[Entity, ...]
    enemies: tuple[Entity, ...]
    visited: tuple[Cell, ...]
    event_lines: tuple[str, ...]
    event_order: tuple[str, ...] = ()
    patrol_turn: int | None = None


@dataclass(frozen=True, slots=True)
class Recording:
    title: str
    source_format: str
    source_version: int
    record_sha256: str
    terrain: tuple[str, ...]
    start: Cell
    exit: Cell
    frames: tuple[Frame, ...]
    final_metrics: tuple[tuple[str, str], ...]
    outcome: str
    reason: str
    development_only: bool

    @property
    def rows(self): return len(self.terrain)

    @property
    def columns(self): return len(self.terrain[0])

    def __post_init__(self):
        if not self.frames or not self.terrain or any(len(r) != len(self.terrain[0]) for r in self.terrain):
            raise ValueError("EMPTY_OR_IRREGULAR_PRESENTATION")


DIRECTIONS = {"MOVE_NORTH": "north", "MOVE_EAST": "east", "MOVE_SOUTH": "south", "MOVE_WEST": "west"}


def heading(before, after, previous="south"):
    """Only an observed displacement supplies a visual facing direction."""
    delta = (after[0] - before[0], after[1] - before[1])
    return {(-1, 0): "north", (0, 1): "east", (1, 0): "south", (0, -1): "west"}.get(delta, previous)


def pose_for(action, accepted, completed, terminal):
    if completed: return "exit"
    if terminal: return "failed"
    if accepted and action in DIRECTIONS: return "move"
    if accepted and action in ("COLLECT", "ENGAGE"): return action.lower()
    return "idle"
