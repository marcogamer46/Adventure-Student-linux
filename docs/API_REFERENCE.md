# Public API reference

Import supported values and contracts from `src.api`. `API_VERSION` is the string `"v1"`. The fixed facade exports 26 names; the guide adds no API, student callback, or public class requirement. Read [Meet the objects](../GUIDE.html#meet-the-objects) for responsibilities and data flow before using this reference.

## Six component contracts

The concrete constructors belong to your six student classes. The exported Protocols describe their instance interfaces; implementing a matching interface is sufficient. Private helpers are allowed.

| Protocol | Student constructor | Required member |
|---|---|---|
| `CharacterContract` | `Character(agent_id)` | Read-only `agent_id: str` |
| `ArtifactContract` | `Artifact(artifact_id, position, value)` | Read-only `artifact_id: str`, `position: Position`, `value: int` |
| `EnemyContract` | `Enemy(enemy_id, position, encounter_penalty)` | Read-only `enemy_id: str`, `position: Position`, `encounter_penalty: int` |
| `AgentControllerContract` | `AgentController()` | `choose_action(self, state: WorldSnapshot, agent_id: str) -> WorldAction` |
| `TerrainGeneratorContract` | `TerrainGenerator()` | `generate_terrain(self, specification: TerrainGenerationSpec, seed: int) -> Terrain` |
| `LevelGeneratorContract` | `LevelGenerator(terrain_generator)` | `generate_level(self, specification: LevelSpecification, seed: int) -> LevelDefinition` |

Entity components expose data, while the framework applies state changes. Generators receive an explicit integer seed. LevelGenerator must use the injected terrain dependency through its stated callback. Supplied-world controller execution does not require a student-generated world. See [editable files](EDITABLE_FILES.md) for the exact workflow prerequisites and allowed boundary.

## Coordinate and terrain values

The data classes below are frozen and slotted. Their constructors validate local types and field shape; complete relationships and original-specification constraints are checked separately by the host. Integers must be actual `int` values, not booleans or coerced strings. Canonical value fields require the exact API types, rather than lookalike dictionaries or foreign subclasses.

| Value | Constructor fields | Helpers and constraints |
|---|---|---|
| `Position` | `Position(row: int, column: int)` | Zero-based coordinate convention. `manhattan_distance(other)` returns the sum of absolute coordinate differences. Construction itself permits negative coordinates; in-bounds validation is separate. |
| `Terrain` | `Terrain(terrain_rows: tuple[str, ...])` | Nonempty rectangular rows, each containing only `#` and `.`. `rows` and `columns` are read-only derived properties. `is_in_bounds(position)` checks dimensions; `is_traversable(position)` checks in-bounds floor geometry. |

The `...` inside `tuple[str, ...]` is type notation for a variable-length tuple, not an omitted executable argument. All runnable examples in the guide provide concrete values. S/E in text diagrams are endpoint overlays; they are not terrain symbols or a parsing assignment. `is_traversable` does not check enemy occupancy, patrol timing, or action legality.

`TerrainTopology` has four members: `GENERAL`, `STRAIGHT_PATH`, `BENT_PATH`, and `BRANCHING_TREE`. Enum values use the corresponding uppercase strings. Topology and complete graph validity belong to specification validation, not merely to constructing a rectangular Terrain.

## Generation requests

`TerrainGenerationSpec` requires keyword arguments. The only defaulted field is `topology=TerrainTopology.GENERAL`.

| Field | Type and meaning |
|---|---|
| `rows`, `columns` | Positive integers; exact dimensions |
| `min_open_tiles`, `max_open_tiles` | Nonnegative integers in ordered inclusive bounds, fitting the board area |
| `max_attempts` | Positive integer generation budget |
| `topology` | Canonical `TerrainTopology` |

`LevelSpecification` also requires keyword arguments. Every field below is required; it has no omitted optional field group.

| Field or fields | Type and meaning |
|---|---|
| `level_id`, `profile_id`, `agent_id` | Nonempty already-trimmed strings identifying the request |
| `terrain_spec` | Canonical `TerrainGenerationSpec` for the injected provider |
| `artifact_count`, `enemy_count` | Exact nonnegative counts |
| `artifact_value_min`, `artifact_value_max` | Inclusive nonnegative value bounds, minimum no greater than maximum |
| `enemy_penalty_min`, `enemy_penalty_max` | Inclusive nonnegative penalty bounds |
| `min_route_moves`, `max_route_moves` | Inclusive bounds on shortest geometric endpoint movement distance, excluding EXIT and encounters |
| `min_branch_tiles` | Nonnegative minimum number of floor tiles with at least three orthogonal floor neighbors |
| `max_dead_end_tiles` | Nonnegative maximum number of floor tiles with one orthogonal floor neighbor |
| `require_alternate_path` | Boolean requirement for an alternate endpoint path |
| `allow_entity_overlap` | Boolean placement permission; it does not make occupied enemy tiles enterable |
| `allow_entities_on_endpoints` | Boolean placement permission |
| `max_turns` | Positive integer logical hard cap H |
| `max_attempts` | Positive integer level-generation attempt budget |

Original family rules can add constraints, such as leaf endpoints in the public tree families. Do not weaken the input request to make a candidate pass. An exhausted finite attempt budget means a generation attempt failed to produce an acceptable candidate within its budget; it is not a mathematical impossibility proof.

The workbench accepts public seeds in the inclusive range 0 through `2**31 - 1`. Same implementation, specification, dependency, and seed must reproduce its own result. Different implementations may generate different valid worlds, and different seeds need not always produce distinct worlds.

## Immutable definitions and adapters

| Value | Constructor | Local constraints |
|---|---|---|
| `CharacterDefinition` | `CharacterDefinition(agent_id)` | Nonempty trimmed string |
| `ArtifactDefinition` | `ArtifactDefinition(artifact_id, position, value)` | Trimmed ID, canonical Position, nonnegative integer value |
| `EnemyDefinition` | `EnemyDefinition(enemy_id, position, encounter_penalty)` | Trimmed ID, canonical Position, nonnegative integer penalty |
| `PatrolDefinition` | `PatrolDefinition(enemy_id=..., positions=..., initial_phase=0)` | Keyword-only; nonempty tuple of Positions; phase indexes that tuple |
| `EnemyObservation` | `EnemyObservation(enemy_id=..., position=..., phase=...)` | Keyword-only; position is Position or None; phase is a nonnegative integer or None |

The last two constructor cells are signature notation, not executable examples. `PatrolDefinition.period` is a read-only derived count. Patrol schedules are visible supplied-world values, not a required student generation output. An active static enemy observation has its current Position and `phase=None`; a defeated static enemy has `position=None`. A visible patrol observation gives its current Position and phase. Full consistency depends on the admitted world.

The following complete value expressions are constructor examples only. They do not constitute a complete admitted level or a student implementation:

```python
from src.api import (
    ArtifactDefinition, CharacterDefinition, EnemyDefinition, EnemyObservation,
    PatrolDefinition, Position, WorldAction, WorldActionType,
)

character_data = CharacterDefinition("explorer")
artifact_data = ArtifactDefinition("artifact-0", Position(0, 2), 25)
enemy_data = EnemyDefinition("enemy-0", Position(0, 1), 6)
patrol_data = PatrolDefinition(
    enemy_id="enemy-0",
    positions=(Position(0, 2), Position(0, 2), Position(1, 2)),
    initial_phase=1,
)
observed_patrol = EnemyObservation(
    enemy_id="enemy-0", position=Position(0, 2), phase=1,
)
collect_value = WorldAction(WorldActionType.COLLECT, target_id="artifact-0")
engage_value = WorldAction(WorldActionType.ENGAGE, target_id="enemy-0")
wait_value = WorldAction.wait()
exit_value = WorldAction(WorldActionType.EXIT)
```

The constructor for a valid action value does not prove that it is legal in the current game state. The patrol and static-enemy examples above are separate field illustrations, not an instruction to engage a patrol.

| Supplied adapter | Input interface | Detached result |
|---|---|---|
| `to_character_definition(source)` | CharacterContract | CharacterDefinition |
| `to_artifact_definition(source)` | ArtifactContract | ArtifactDefinition |
| `to_enemy_definition(source)` | EnemyContract | EnemyDefinition |

Each adapter captures the required properties once, validates the captured values, and constructs detached immutable data. Missing/failing getters and invalid values produce `ContractViolation`. Implementing an entity class remains required even though a typed-data illustration directly constructs its result type.

## Complete level value

`LevelDefinition` is keyword-only. It detaches terrain, coordinates, and definitions; entity tuples are sorted by their IDs. The field list is:

| Field | Type | Default |
|---|---|---|
| `level_id`, `profile_id` | Trimmed nonempty strings | Required |
| `seed` | Nonnegative integer | Required |
| `terrain` | Terrain | Required |
| `start`, `exit` | Position | Required |
| `character` | CharacterDefinition | Required |
| `artifacts` | Tuple of ArtifactDefinition | `()` |
| `enemies` | Tuple of EnemyDefinition | `()` |
| `patrols` | Tuple of PatrolDefinition | `()` |

The [opening typed values](../examples/guide/opening_typed_values.py) provide a full executable LevelSpecification and LevelDefinition. The [opening canonical level](../examples/guide/opening-canonical-level.json) is a stored representation. The [prepared input](../examples/guide/levels/reach-the-exit.json) wraps stored level data with its original request, configuration, and public admission proof. Callbacks receive typed objects, not these JSON envelopes.

Local construction does not establish unique IDs, connected floor, legal placement, original-specification compliance, or instructor eligibility. Public admission and local integrity are distinct from grading, certification, authorship, and publication.

## Current snapshot

`WorldSnapshot` is keyword-only immutable callback input. Initial level definitions persist after collection or engagement. Use current position, removed IDs, and observations to determine the current situation.

| Field | Type and meaning | Default |
|---|---|---|
| `level` | LevelDefinition, including initial definitions and visible schedules | Required |
| `agent_position` | Current Position | Required |
| `turn` | Nonnegative accepted-action count | Required |
| `collected_artifact_ids` | Tuple of trimmed ID strings; locally sorted | Required |
| `defeated_enemy_ids` | Tuple of trimmed ID strings; locally sorted | Required |
| `base_points` | Nonnegative integer B | Required |
| `deduction_rate` | Nonnegative integer r | Required |
| `baseline_cost` | Positive integer L | Required |
| `zero_score_excess` | Positive integer Q | Required |
| `max_turns` | Positive integer H | Required |
| `deadline_turn` | Positive integer D or None | `None` |
| `allowed_actions` | Tuple of distinct WorldActionType values | Four movement directions, WAIT, EXIT |
| `enemy_observations` | Tuple of EnemyObservation, sorted by ID | `()` |

The constructor default vocabulary is not a table of what the current public runtime enables. Actual public snapshots also enable COLLECT and ENGAGE, including in the entity-free case. INTERACT is absent. Read the snapshot and check destinations/targets; an enabled kind does not make every use legal.

Read-only convenience properties are `level_id`, `seed`, `agent_id`, `terrain`, `rows`, `columns`, `start_position`, and `exit_position`. `is_in_bounds(position)` and `is_traversable(position)` delegate to terrain geometry. There is no mutable position setter, score accumulator property, movement method, or public `patrol_turn` field. Replay's saved patrol-clock metadata helps describe terminal frames but does not extend this API. No post-completion snapshot is sent to another controller callback.

## Actions and legality

`WorldAction(action_type, *, target_id=None)` requires a canonical WorldActionType. `target_id`, when supplied, must be a nonempty trimmed string. `WorldAction.wait()` constructs a WAIT value.

| Enum member | Current public rule |
|---|---|
| `MOVE_NORTH` | Row minus one; destination must be in-bounds floor and unoccupied by an undefeated enemy at action start |
| `MOVE_SOUTH` | Row plus one, with the same checks |
| `MOVE_WEST` | Column minus one, with the same checks |
| `MOVE_EAST` | Column plus one, with the same checks |
| `COLLECT` | Target the ID of an available artifact on the current tile; award once and remain in place |
| `ENGAGE` | Target an undefeated orthogonally adjacent static enemy; add its penalty once and remain in place |
| `WAIT` | Use one turn without movement; a later patrol step can still collide |
| `EXIT` | Return while on the exit; accepted EXIT uses a turn and completes before another patrol movement |
| `INTERACT` | Defined enum member but disabled in these public gameplay rules |

Movement, WAIT, and EXIT require no target. COLLECT and ENGAGE require the correct target ID. Patrols cannot be engaged. Illegal actions terminate immediately without a replacement WAIT, accepted-turn increment, or patrol advance. A bare string such as `"EXIT"`, None, or an arbitrary object is malformed callback output.

For patrol execution, action validation uses occupancy at action start. After a non-EXIT accepted action, patrol movement occurs before collision, deadline, and hard-cap checks. The [patrol guidance](../GUIDE.html#keep-extending-the-same-solution) explains where to find each selected world's complete timing rules. The [action and points overview](../GUIDE.html#know-what-an-action-does) explains current metrics; Help in the workbench provides the full formula and actual limits.

## Diagnostic values

`ContractViolation(component: str, field: str, reason: str)` exposes read-only `component`, `field`, and `reason`. `GenerationFailure(component: str, reason: str)` exposes read-only `component` and `reason`. All diagnostic constructor fields require strings. They describe a failed contract or generation attempt; they are not grades or a proof that a world cannot be solved.

The 26 exports are API_VERSION; Position; Terrain; WorldActionType; WorldAction; WorldSnapshot; the six Contracts above; TerrainTopology; TerrainGenerationSpec; LevelSpecification; LevelDefinition; CharacterDefinition; ArtifactDefinition; EnemyDefinition; PatrolDefinition; EnemyObservation; the three adapters above; ContractViolation; and GenerationFailure. The implementation boundary remains the same throughout [the seven base cases and further workbench variations](../GUIDE.html#seven-base-cases).
