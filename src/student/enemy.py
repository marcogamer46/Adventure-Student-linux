"""TODO: implement initial enemy data; introductory gameplay has no enemies."""
from src.api import EnemyDefinition, Position


class Enemy:
    """Expose read-only identity, position, and nonnegative encounter penalty."""

    def __init__(self, enemy_id: str, position: Position, encounter_penalty: int) -> None:
        raise NotImplementedError("TODO Enemy: implement constructor and properties")

    @property
    def enemy_id(self) -> str:
        raise NotImplementedError("TODO Enemy.enemy_id")

    @property
    def position(self) -> Position:
        raise NotImplementedError("TODO Enemy.position")

    @property
    def encounter_penalty(self) -> int:
        raise NotImplementedError("TODO Enemy.encounter_penalty")
