"""Inclusive initial entity ranges, composing inventory and original binding."""

from __future__ import annotations

from src.api import LevelDefinition, LevelSpecification
from src.framework.level_entity_inventory_validation import (
    LevelEntityInventoryValidationError, validate_level_entity_inventory_candidate,
)

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "INVENTORY_INVALID", "INVALID_ARTIFACT",
    "INVALID_ENEMY", "ARTIFACT_VALUE_OUT_OF_RANGE", "ENEMY_PENALTY_OUT_OF_RANGE",
})


class LevelEntityRangeValidationError(ValueError):
    """A read-only finite code, with no payload or nested diagnostic text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level entity range validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _capture_numbers(entities: tuple, field: str, code: str) -> tuple[int, ...]:
    # Task 014 has proven exact tuple and canonical entry types. Capture local
    # numeric shapes without consulting IDs, positions or other entity fields.
    values = []
    for entity in entities:
        try:
            value = getattr(entity, field)
        except AttributeError:
            raise LevelEntityRangeValidationError(code) from None
        if type(value) is not int or value < 0:
            raise LevelEntityRangeValidationError(code)
        values.append(value)
    return tuple(values)


def validate_level_entity_range_candidate(
    level: LevelDefinition, specification: LevelSpecification, original_seed: int,
) -> None:
    """Check original inclusive ranges after the unchanged Tasks 014–010 chain.

    Check order: outer types, range local shapes/ordering, Task 014, all artifact
    numeric shapes, all enemy numeric shapes, artifact ranges, enemy ranges.
    Empty inventories still require valid intervals. Zero is legal if allowed;
    only the supplied intervals bound exact nonnegative built-in integers.
    No aggregate reward, balancing, score, placement or patrol rule is applied.
    Success is limited conformance evidence, not full admission/certification.
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelEntityRangeValidationError("WRONG_TYPE")
    try:
        artifact_min = specification.artifact_value_min
        artifact_max = specification.artifact_value_max
        enemy_min = specification.enemy_penalty_min
        enemy_max = specification.enemy_penalty_max
    except AttributeError:
        raise LevelEntityRangeValidationError("INVALID_SPECIFICATION") from None
    if any(type(value) is not int or value < 0
           for value in (artifact_min, artifact_max, enemy_min, enemy_max)):
        raise LevelEntityRangeValidationError("INVALID_SPECIFICATION")
    if artifact_min > artifact_max or enemy_min > enemy_max:
        raise LevelEntityRangeValidationError("INVALID_SPECIFICATION")

    try:
        validate_level_entity_inventory_candidate(level, specification, original_seed)
    except LevelEntityInventoryValidationError:
        raise LevelEntityRangeValidationError("INVENTORY_INVALID") from None

    # Capture both complete numeric inventories before checking any interval.
    # A malformed later payload therefore precedes an earlier range violation.
    artifact_values = _capture_numbers(level.artifacts, "value", "INVALID_ARTIFACT")
    enemy_penalties = _capture_numbers(level.enemies, "encounter_penalty", "INVALID_ENEMY")
    if any(not artifact_min <= value <= artifact_max for value in artifact_values):
        raise LevelEntityRangeValidationError("ARTIFACT_VALUE_OUT_OF_RANGE")
    if any(not enemy_min <= penalty <= enemy_max for penalty in enemy_penalties):
        raise LevelEntityRangeValidationError("ENEMY_PENALTY_OUT_OF_RANGE")
