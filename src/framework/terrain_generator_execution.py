"""One terrain generator call with detached inputs and independent validation."""

from __future__ import annotations

from src.api import GenerationFailure, Terrain, TerrainGenerationSpec, TerrainGeneratorContract, TerrainTopology
from src.framework.terrain_validation import TerrainValidationError, validate_terrain_candidate

_ERROR_CODES = frozenset({
    "INVALID_SPECIFICATION", "INVALID_SEED", "GENERATOR_CONTRACT_ERROR",
    "GENERATOR_REPORTED_FAILURE", "GENERATOR_EXCEPTION", "INVALID_RETURN",
    "TERRAIN_INVALID",
})


class TerrainGeneratorExecutionError(RuntimeError):
    """A read-only finite execution code without component or nested text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown terrain generator execution code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _copy_specifications(
    specification: TerrainGenerationSpec,
) -> tuple[TerrainGenerationSpec, TerrainGenerationSpec]:
    if type(specification) is not TerrainGenerationSpec:
        raise TerrainGeneratorExecutionError("INVALID_SPECIFICATION")
    try:
        # Capture each original field once. The component receives neither the
        # host object nor the separate copy that defines validation authority.
        fields = dict(
            rows=specification.rows, columns=specification.columns,
            min_open_tiles=specification.min_open_tiles,
            max_open_tiles=specification.max_open_tiles,
            max_attempts=specification.max_attempts, topology=specification.topology,
        )
        call_specification = TerrainGenerationSpec(**fields)
        # Exact enum type alone can admit forged, nonmember enum objects.
        if not any(fields["topology"] is member for member in TerrainTopology):
            raise TerrainGeneratorExecutionError("INVALID_SPECIFICATION")
        validation_specification = TerrainGenerationSpec(**fields)
    except (AttributeError, TypeError, ValueError):
        raise TerrainGeneratorExecutionError("INVALID_SPECIFICATION") from None
    return call_specification, validation_specification


def execute_terrain_generator_once(
    generator: TerrainGeneratorContract, specification: TerrainGenerationSpec, seed: int,
) -> Terrain:
    """Call only the documented member once; return a detached valid Terrain.

    Order: specification type/local shape, seed, member access/callability, one
    call, exact returned type, Task 010, detached return. max_attempts is passed
    as component input and never causes host retries. This in-process boundary
    does not check determinism, discover components or execute a level/runtime.
    """
    call_specification, validation_specification = _copy_specifications(specification)
    if type(seed) is not int or seed < 0:
        raise TerrainGeneratorExecutionError("INVALID_SEED")
    try:
        method = generator.generate_terrain
    except Exception:
        raise TerrainGeneratorExecutionError("GENERATOR_CONTRACT_ERROR") from None
    if not callable(method):
        raise TerrainGeneratorExecutionError("GENERATOR_CONTRACT_ERROR")
    try:
        candidate = method(call_specification, seed)
    except GenerationFailure:
        raise TerrainGeneratorExecutionError("GENERATOR_REPORTED_FAILURE") from None
    except Exception:
        raise TerrainGeneratorExecutionError("GENERATOR_EXCEPTION") from None
    if type(candidate) is not Terrain:
        raise TerrainGeneratorExecutionError("INVALID_RETURN")
    try:
        validate_terrain_candidate(candidate, validation_specification)
    except TerrainValidationError:
        raise TerrainGeneratorExecutionError("TERRAIN_INVALID") from None
    try:
        return Terrain(tuple(row for row in candidate.terrain_rows))
    except (AttributeError, TypeError, ValueError):
        raise TerrainGeneratorExecutionError("TERRAIN_INVALID") from None
