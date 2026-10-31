"""Structural instance contracts; concrete constructors are checked separately."""

from __future__ import annotations

from typing import Protocol
from ._values import (
    LevelDefinition, LevelSpecification, Position, Terrain, TerrainGenerationSpec,
    WorldAction, WorldSnapshot,
)


class CharacterContract(Protocol):
    @property
    def agent_id(self) -> str: ...


class ArtifactContract(Protocol):
    @property
    def artifact_id(self) -> str: ...
    @property
    def position(self) -> Position: ...
    @property
    def value(self) -> int: ...


class EnemyContract(Protocol):
    @property
    def enemy_id(self) -> str: ...
    @property
    def position(self) -> Position: ...
    @property
    def encounter_penalty(self) -> int: ...


class AgentControllerContract(Protocol):
    def choose_action(
        self, state: WorldSnapshot, agent_id: str,
    ) -> WorldAction: ...


class TerrainGeneratorContract(Protocol):
    def generate_terrain(
        self, specification: TerrainGenerationSpec, seed: int,
    ) -> Terrain: ...


class LevelGeneratorContract(Protocol):
    def generate_level(
        self, specification: LevelSpecification, seed: int,
    ) -> LevelDefinition: ...
