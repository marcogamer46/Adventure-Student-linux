"""Typed data illustration, not a student implementation or a CLI input parser.
Use the pinned Adventure package as the import environment.
This file builds public values; it neither runs student code nor solves the level.
"""
from src.api import (
    CharacterDefinition, LevelDefinition, LevelSpecification, Position,
    Terrain, TerrainGenerationSpec, TerrainTopology, WorldAction, WorldActionType,
)

terrain_spec = TerrainGenerationSpec(
    rows=1, columns=5, min_open_tiles=5, max_open_tiles=5,
    max_attempts=3, topology=TerrainTopology.STRAIGHT_PATH,
)

level_spec = LevelSpecification(
    level_id="adventure-t0-a", profile_id="ADV-T0-A-DEV", agent_id="explorer",
    terrain_spec=terrain_spec, artifact_count=0, enemy_count=0,
    artifact_value_min=0, artifact_value_max=0,
    enemy_penalty_min=0, enemy_penalty_max=0,
    min_route_moves=4, max_route_moves=4,
    min_branch_tiles=0, max_dead_end_tiles=5,
    require_alternate_path=False, allow_entity_overlap=False,
    allow_entities_on_endpoints=False, max_turns=32, max_attempts=3,
)

# One concrete possible returned value, not an implementation of either generator.
terrain = Terrain((".....",))
level = LevelDefinition(
    level_id=level_spec.level_id, profile_id=level_spec.profile_id, seed=11,
    terrain=terrain, start=Position(0, 0), exit=Position(0, 4),
    character=CharacterDefinition(level_spec.agent_id),
    artifacts=(), enemies=(), patrols=(),
)

# Two examples of values the controller can return at appropriate states.
one_step_east = WorldAction(WorldActionType.MOVE_EAST)
accepted_exit_intention = WorldAction(WorldActionType.EXIT)
# The second is legal only when the current explorer position equals the exit.
# No controller, terrain-generation, or level-generation algorithm is supplied.
