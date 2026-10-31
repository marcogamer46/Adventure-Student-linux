"""Exact entity counts and combined ID uniqueness, composing original binding."""

from __future__ import annotations

from src.api import ArtifactDefinition, EnemyDefinition, LevelDefinition, LevelSpecification
from src.framework.level_identity_validation import LevelIdentityValidationError, validate_level_identity_candidate

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_SPECIFICATION", "IDENTITY_INVALID", "INVALID_LEVEL",
    "ARTIFACT_COUNT_MISMATCH", "ENEMY_COUNT_MISMATCH", "INVALID_ARTIFACT",
    "INVALID_ENEMY", "DUPLICATE_ENTITY_ID",
})


class LevelEntityInventoryValidationError(ValueError):
    """A read-only finite code, with no entity or nested diagnostic text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level entity inventory validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _entity_ids(entities: tuple, field: str, code: str) -> tuple[str, ...]:
    # The caller has already proven exact tuple and canonical entry types.
    # Capture every ID before hashing/comparing any ID for uniqueness.
    identities = []
    for entity in entities:
        try:
            identity = getattr(entity, field)
        except AttributeError:
            raise LevelEntityInventoryValidationError(code) from None
        if type(identity) is not str or identity == "" or identity != identity.strip():
            raise LevelEntityInventoryValidationError(code)
        identities.append(identity)
    return tuple(identities)


def validate_level_entity_inventory_candidate(
    level: LevelDefinition, specification: LevelSpecification, original_seed: int,
) -> None:
    """Require the original exact inventory and one artifact/enemy ID namespace.

    Check order: outer types, requested count shape, Task 013, collection shape,
    artifact/enemy count equality, artifact/enemy ID shape, combined uniqueness.
    Task 013 retains Tasks 012–010. Counts are not maxima. Other identities are
    separate namespaces; IDs are never normalized, renamed or deduplicated.
    Values, positions, overlap and patrol relationships remain unread here.
    Success is inventory evidence, not full admission or profile approval.
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelEntityInventoryValidationError("WRONG_TYPE")
    try:
        artifact_count = specification.artifact_count
        enemy_count = specification.enemy_count
    except AttributeError:
        raise LevelEntityInventoryValidationError("INVALID_SPECIFICATION") from None
    if (type(artifact_count) is not int or artifact_count < 0
            or type(enemy_count) is not int or enemy_count < 0):
        raise LevelEntityInventoryValidationError("INVALID_SPECIFICATION")

    # Do not access any candidate collection before original-input binding and
    # the complete composed structural boundary succeed.
    try:
        validate_level_identity_candidate(level, specification, original_seed)
    except LevelIdentityValidationError:
        raise LevelEntityInventoryValidationError("IDENTITY_INVALID") from None

    try:
        artifacts = level.artifacts
        enemies = level.enemies
    except AttributeError:
        raise LevelEntityInventoryValidationError("INVALID_LEVEL") from None
    if type(artifacts) is not tuple or type(enemies) is not tuple:
        raise LevelEntityInventoryValidationError("INVALID_LEVEL")
    if (any(type(entity) is not ArtifactDefinition for entity in artifacts)
            or any(type(entity) is not EnemyDefinition for entity in enemies)):
        raise LevelEntityInventoryValidationError("INVALID_LEVEL")

    if len(artifacts) != artifact_count:
        raise LevelEntityInventoryValidationError("ARTIFACT_COUNT_MISMATCH")
    if len(enemies) != enemy_count:
        raise LevelEntityInventoryValidationError("ENEMY_COUNT_MISMATCH")

    artifact_ids = _entity_ids(artifacts, "artifact_id", "INVALID_ARTIFACT")
    enemy_ids = _entity_ids(enemies, "enemy_id", "INVALID_ENEMY")
    seen = set()
    for identity in artifact_ids + enemy_ids:
        if identity in seen:
            raise LevelEntityInventoryValidationError("DUPLICATE_ENTITY_ID")
        seen.add(identity)
