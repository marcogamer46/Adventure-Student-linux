"""Bind a candidate to original host identities/seed, then validate structure."""

from __future__ import annotations

from src.api import CharacterDefinition, LevelDefinition, LevelSpecification
from src.framework.level_shape_validation import LevelShapeValidationError, validate_level_shape_candidate

_ERROR_CODES = frozenset({
    "WRONG_TYPE", "INVALID_ORIGINAL_SEED", "INVALID_SPECIFICATION", "INVALID_LEVEL",
    "LEVEL_ID_MISMATCH", "PROFILE_ID_MISMATCH", "AGENT_ID_MISMATCH", "SEED_MISMATCH",
    "SHAPE_INVALID",
})


class LevelIdentityValidationError(ValueError):
    """A read-only finite code, with no candidate or nested diagnostic text."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown level identity validation code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _valid_identity(value: object) -> bool:
    # Check the exact type before any comparison or string operation. The
    # stripped value is only a validity probe; no identity is normalized.
    return type(value) is str and value != "" and value == value.strip()


def validate_level_identity_candidate(
    level: LevelDefinition, specification: LevelSpecification, original_seed: int,
) -> None:
    """Require exact original-input binding before composing Tasks 010–012.

    The caller supplies the trusted original specification and base seed;
    neither is inferred from candidate content or a derived retry seed.
    Profile equality is consistency only, not registry approval or a credential.
    Success does not admit entities, certify a level or activate any runtime.
    """
    if type(level) is not LevelDefinition or type(specification) is not LevelSpecification:
        raise LevelIdentityValidationError("WRONG_TYPE")
    if type(original_seed) is not int or original_seed < 0:
        raise LevelIdentityValidationError("INVALID_ORIGINAL_SEED")

    try:
        expected_level = specification.level_id
        expected_profile = specification.profile_id
        expected_agent = specification.agent_id
    except AttributeError:
        raise LevelIdentityValidationError("INVALID_SPECIFICATION") from None
    if not all(_valid_identity(value) for value in (expected_level, expected_profile, expected_agent)):
        raise LevelIdentityValidationError("INVALID_SPECIFICATION")

    try:
        candidate_level = level.level_id
        candidate_profile = level.profile_id
        candidate_seed = level.seed
        character = level.character
    except AttributeError:
        raise LevelIdentityValidationError("INVALID_LEVEL") from None
    if type(character) is not CharacterDefinition:
        raise LevelIdentityValidationError("INVALID_LEVEL")
    try:
        candidate_agent = character.agent_id
    except AttributeError:
        raise LevelIdentityValidationError("INVALID_LEVEL") from None
    if (not all(_valid_identity(value) for value in (candidate_level, candidate_profile, candidate_agent))
            or type(candidate_seed) is not int or candidate_seed < 0):
        raise LevelIdentityValidationError("INVALID_LEVEL")

    # All operands are now exact safe primitives. Precedence is level, profile,
    # actor, seed. No graph work is done for a substituted or malformed identity.
    if candidate_level != expected_level:
        raise LevelIdentityValidationError("LEVEL_ID_MISMATCH")
    if candidate_profile != expected_profile:
        raise LevelIdentityValidationError("PROFILE_ID_MISMATCH")
    if candidate_agent != expected_agent:
        raise LevelIdentityValidationError("AGENT_ID_MISMATCH")
    if candidate_seed != original_seed:
        raise LevelIdentityValidationError("SEED_MISMATCH")

    try:
        validate_level_shape_candidate(level, specification)
    except LevelShapeValidationError:
        raise LevelIdentityValidationError("SHAPE_INVALID") from None
