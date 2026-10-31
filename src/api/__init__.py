"""Instructor-owned cumulative public v1 data and contracts; no runtime imports."""

from ._values import (
    Position, Terrain, WorldActionType, WorldAction, WorldSnapshot,
    TerrainTopology, TerrainGenerationSpec, LevelSpecification, LevelDefinition,
    CharacterDefinition, ArtifactDefinition, EnemyDefinition,
    PatrolDefinition, EnemyObservation, ContractViolation, GenerationFailure,
)
from ._contracts import (
    CharacterContract, ArtifactContract, EnemyContract, AgentControllerContract,
    TerrainGeneratorContract, LevelGeneratorContract,
)
from ._adapters import to_character_definition, to_artifact_definition, to_enemy_definition

API_VERSION: str = "v1"

__all__ = [
    "API_VERSION", "Position", "Terrain", "WorldActionType", "WorldAction",
    "WorldSnapshot", "CharacterContract", "ArtifactContract", "EnemyContract",
    "AgentControllerContract", "TerrainGeneratorContract", "LevelGeneratorContract",
    "TerrainTopology", "TerrainGenerationSpec", "LevelSpecification", "LevelDefinition",
    "CharacterDefinition", "ArtifactDefinition", "EnemyDefinition",
    "PatrolDefinition", "EnemyObservation", "to_character_definition",
    "to_artifact_definition", "to_enemy_definition", "ContractViolation", "GenerationFailure",
]
