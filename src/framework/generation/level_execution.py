"""One static level call, full ownership, and observable terrain dependency calls."""

from __future__ import annotations

from copy import deepcopy

from src.api import GenerationFailure, LevelDefinition, LevelSpecification, TerrainTopology
from src.framework import (
    level_entity_inventory_validation as inventory_validation,
    level_entity_placement_validation as placement_validation,
    level_entity_range_validation as range_validation,
    level_identity_validation as identity_validation,
    level_patrol_validation as patrol_validation,
    level_route_validation as route_validation,
    level_shape_validation as shape_validation,
    terrain_validation,
)
from src.framework.terrain_generator_execution import (
    TerrainGeneratorExecutionError, execute_terrain_generator_once,
)
from .canonical import (
    CanonicalError, canonical_bytes, digest, level_record, level_request,
    read_level, read_level_request, read_terrain, terrain_record, terrain_request,
)

LEVEL_CODES = frozenset({
    "INVALID_SPECIFICATION", "INVALID_SEED", "CONTRADICTORY_SPECIFICATION",
    "GENERATOR_CONTRACT_ERROR", "GENERATOR_REPORTED_FAILURE", "GENERATOR_EXCEPTION",
    "INVALID_RETURN", "LEVEL_INVALID",
})
DEPENDENCY_CODES = frozenset({
    "DEPENDENCY_SPECIFICATION", "DEPENDENCY_SEED", "DEPENDENCY_BUDGET",
    "DEPENDENCY_DURING_CONSTRUCTION", "DEPENDENCY_FACTORY_EXCEPTION",
    "SHARED_DEPENDENCY",
})
_VALIDATORS = (
    (patrol_validation.LevelPatrolValidationError, "level-patrol", patrol_validation._ERROR_CODES),
    (placement_validation.LevelEntityPlacementValidationError, "level-placement", placement_validation._ERROR_CODES),
    (range_validation.LevelEntityRangeValidationError, "level-range", range_validation._ERROR_CODES),
    (inventory_validation.LevelEntityInventoryValidationError, "level-inventory", inventory_validation._ERROR_CODES),
    (identity_validation.LevelIdentityValidationError, "level-identity", identity_validation._ERROR_CODES),
    (shape_validation.LevelShapeValidationError, "level-shape", shape_validation._ERROR_CODES),
    (route_validation.LevelRouteValidationError, "level-route", route_validation._ERROR_CODES),
    (terrain_validation.TerrainValidationError, "terrain-validation", terrain_validation._ERROR_CODES),
)
LEVEL_STAGES = frozenset({"level-input", "level-execution", "level-validation",
                          "terrain-dependency", "dependency-construction"}
                         | {stage for _, stage, _ in _VALIDATORS})
LEVEL_DETAIL_CODES = frozenset(code for _, _, codes in _VALIDATORS for code in codes)


class LevelExecutionError(RuntimeError):
    """Bounded classification, optionally retaining one owned validator detail."""

    def __init__(self, code: str, *, stage: str | None = None, detail_code: str | None = None):
        if type(code) is not str or code not in LEVEL_CODES:
            raise ValueError("Unknown level execution code.")
        if stage is None:
            stage = "level-input" if code in {"INVALID_SPECIFICATION", "INVALID_SEED",
                                               "CONTRADICTORY_SPECIFICATION"} else "level-execution"
        if type(stage) is not str or stage not in LEVEL_STAGES:
            raise ValueError("Unknown level execution stage.")
        if detail_code is not None and (type(detail_code) is not str or detail_code not in LEVEL_DETAIL_CODES):
            raise ValueError("Unknown level validator detail.")
        self._code, self._stage, self._detail_code = code, stage, detail_code
        super().__init__(code)

    @property
    def code(self):
        return self._code

    @property
    def stage(self):
        return self._stage

    @property
    def detail_code(self):
        return self._detail_code


def _validator_detail(error: BaseException) -> tuple[str, str | None]:
    """Follow only exact owned wrappers, never arbitrary component context."""
    stage, detail = "level-validation", None
    seen = set()
    while id(error) not in seen:
        seen.add(id(error))
        entry = next((entry for entry in _VALIDATORS if type(error) is entry[0]), None)
        if entry is None:
            break
        value = error.code
        if type(value) is not str or value not in entry[2]:
            break
        stage, detail = entry[1], value
        error = BaseException.__context__.__get__(error)
        if error is None:
            break
    return stage, detail


def preflight_level_request(specification: LevelSpecification, seed: int) -> tuple[LevelSpecification, int]:
    """Capture every local field and reject direct public contradictions only.

    These necessary bounds are not a general feasibility solver. Passing them
    does not certify legal completion within H or establish a baseline L.
    """
    try:
        spec, original_seed = read_level_request(level_request(specification, seed))
    except CanonicalError as error:
        code = "INVALID_SEED" if error.code == "INVALID_SEED" else "INVALID_SPECIFICATION"
        raise LevelExecutionError(code) from None
    terrain = spec.terrain_spec
    topology = terrain.topology
    opens = terrain.max_open_tiles
    if topology is TerrainTopology.STRAIGHT_PATH:
        # The declared area bound cannot enlarge a single row/column path.
        opens = min(opens, max(terrain.rows, terrain.columns))
    if topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH):
        # Forced leaf endpoints take N-1 moves plus EXIT, hence N<=H.
        opens = min(opens, spec.max_route_moves + 1, spec.max_turns)
    route_minimum = max(1, spec.min_route_moves)
    contradiction = (
        opens < 2 or spec.max_route_moves < route_minimum
        or route_minimum > opens - 1 or route_minimum + 1 > spec.max_turns
        or spec.min_branch_tiles > opens
    )
    path = topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH)
    if path:
        contradiction |= (spec.min_branch_tiles > 0 or spec.max_dead_end_tiles < 2
                          or spec.require_alternate_path)
        # On a path the chosen ends are the two leaves, so distance is N-1.
        minimum_path_tiles = 3 if topology is TerrainTopology.BENT_PATH else 2
        contradiction |= max(minimum_path_tiles, terrain.min_open_tiles, route_minimum + 1) > min(
            opens, spec.max_route_moves + 1, spec.max_turns)
    if topology is TerrainTopology.STRAIGHT_PATH:
        contradiction |= max(2, terrain.min_open_tiles, route_minimum + 1) > max(terrain.rows, terrain.columns)
    if topology is TerrainTopology.BENT_PATH:
        contradiction |= terrain.rows < 2 or terrain.columns < 2 or opens < 3
    can_branch = ((terrain.rows >= 2 and terrain.columns >= 3)
                  or (terrain.rows >= 3 and terrain.columns >= 2))
    if topology is TerrainTopology.BRANCHING_TREE:
        branches = max(1, spec.min_branch_tiles)
        contradiction |= (not can_branch or opens < 2 * branches + 2
                          or spec.max_dead_end_tiles < branches + 2 or spec.require_alternate_path)
    if spec.min_branch_tiles > 0:
        contradiction |= not can_branch or opens < 4
    if spec.require_alternate_path:
        contradiction |= terrain.rows < 2 or terrain.columns < 2 or opens < 4
    if terrain.rows == 1 or terrain.columns == 1:
        contradiction |= spec.max_dead_end_tiles < 2
    entities = spec.artifact_count + spec.enemy_count
    available = opens if spec.allow_entities_on_endpoints else opens - 2
    if not spec.allow_entity_overlap:
        contradiction |= entities > available
        if spec.allow_entities_on_endpoints:
            contradiction |= spec.enemy_count > opens - 1
    elif entities and available < 1:
        contradiction = True
    if contradiction:
        raise LevelExecutionError("CONTRADICTORY_SPECIFICATION")
    return spec, original_seed


def execute_level_generator_once(generator: object, specification: LevelSpecification, seed: int) -> LevelDefinition:
    """One documented invocation; validate source then the exact owned snapshot."""
    validation_spec, original_seed = preflight_level_request(specification, seed)
    call_spec, _ = read_level_request(level_request(validation_spec, original_seed))
    try:
        method = generator.generate_level
    except Exception:
        raise LevelExecutionError("GENERATOR_CONTRACT_ERROR") from None
    if not callable(method):
        raise LevelExecutionError("GENERATOR_CONTRACT_ERROR")
    try:
        candidate = method(call_spec, original_seed)
    except GenerationFailure:
        raise LevelExecutionError("GENERATOR_REPORTED_FAILURE") from None
    except Exception:
        raise LevelExecutionError("GENERATOR_EXCEPTION") from None
    if type(candidate) is not LevelDefinition:
        raise LevelExecutionError("INVALID_RETURN")
    try:
        patrol_validation.validate_level_patrol_candidate(candidate, validation_spec, original_seed,
                                                         provenance="student-static")
    except patrol_validation.LevelPatrolValidationError as error:
        stage, detail = _validator_detail(error)
        raise LevelExecutionError("LEVEL_INVALID", stage=stage, detail_code=detail) from None
    try:
        owned = read_level(level_record(candidate))
    except CanonicalError:
        raise LevelExecutionError("LEVEL_INVALID", stage="level-validation") from None
    try:
        patrol_validation.validate_level_patrol_candidate(owned, validation_spec, original_seed,
                                                         provenance="student-static")
    except patrol_validation.LevelPatrolValidationError as error:
        stage, detail = _validator_detail(error)
        raise LevelExecutionError("LEVEL_INVALID", stage=stage, detail_code=detail) from None
    return owned


class _DependencyObserver:
    """Private host observer; the assembler sees a facade with one public method.

    Trace copies on uninvoked constructor-failure trials refer to the same
    construction event for that instance, not additional provider invocations.
    Internal attempt boundaries are unobservable. Increasing derived seeds can
    skip attempts that did not call terrain; only total calls/seed bounds are
    checked. A trial is never an outer generation retry.
    """

    def __init__(self, provider: object):
        self.provider = provider
        self.trace = []
        self.active = False
        self.specification = None
        self.seed = None
        self.last_seed = None
        observer = self

        class TerrainDependency:
            __slots__ = ()

            def generate_terrain(self, specification, seed):
                return observer._invoke(specification, seed)

        self.facade = TerrainDependency()

    def begin(self, specification: LevelSpecification, seed: int) -> None:
        self.specification, self.seed = read_level_request(level_request(specification, seed))
        self.last_seed = self.seed - 1
        self.trace = []
        self.active = True

    def snapshot(self) -> list:
        return deepcopy(self.trace)

    def _invoke(self, specification, seed):
        call = len(self.trace) + 1
        entry = dict(call=call, request=None, invoked=False, status="FAIL", category="DEPENDENCY_FAILURE",
                     code="DEPENDENCY_SPECIFICATION", stage="terrain-dependency", detail_code=None,
                     candidate=None, digest=None)
        try:
            entry["request"] = terrain_request(specification, seed)
        except CanonicalError as error:
            if error.code == "INVALID_SEED":
                entry["code"] = "DEPENDENCY_SEED"
        if not self.active:
            entry.update(code="DEPENDENCY_DURING_CONSTRUCTION", stage="dependency-construction")
        elif call > self.specification.max_attempts:
            entry["code"] = "DEPENDENCY_BUDGET"
        elif entry["request"] is not None:
            expected = terrain_request(self.specification.terrain_spec, self.seed)
            if entry["request"]["specification"] != expected["specification"]:
                entry["code"] = "DEPENDENCY_SPECIFICATION"
            elif ((call == 1 and seed != self.seed)
                  or (call > 1 and not self.seed < seed < self.seed + self.specification.max_attempts)
                  or seed <= self.last_seed):
                entry["code"] = "DEPENDENCY_SEED"
            else:
                self.last_seed = seed
                entry["invoked"] = True
                try:
                    candidate = execute_terrain_generator_once(self.provider, specification, seed)
                except TerrainGeneratorExecutionError as error:
                    # Importing this helper is safe here; determinism only imports
                    # level support lazily so terrain-only imports stay narrow.
                    from .determinism import _diagnostic
                    _, stage, detail = _diagnostic(error)
                    entry.update(code=error.code, stage=stage, detail_code=detail)
                else:
                    record = terrain_record(candidate)
                    entry.update(status="PASS", category="SUCCESS", code="OK",
                                 stage="terrain-validation", candidate=record, digest=digest(record))
        self.trace.append(entry)
        if entry["status"] != "PASS":
            raise GenerationFailure("DEPENDENCY_FAILURE", "Controlled terrain dependency failure.")
        # This second snapshot belongs to the assembler. The trace retains only
        # its already captured primitives, immune to later canonical-slot edits.
        return read_terrain(entry["candidate"])
