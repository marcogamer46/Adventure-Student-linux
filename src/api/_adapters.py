"""Capture once, validate locally, and detach student entity data."""

from __future__ import annotations

from ._contracts import ArtifactContract, CharacterContract, EnemyContract
from ._values import (
    ArtifactDefinition, CharacterDefinition, ContractViolation, EnemyDefinition,
    Position, _exact, _identity, _integer,
)


def to_character_definition(source: CharacterContract) -> CharacterDefinition:
    try:
        captured = source.agent_id
    except AttributeError:
        raise ContractViolation("Character", "agent_id", "missing member") from None
    except Exception:
        raise ContractViolation("Character", "agent_id", "getter failed") from None
    try:
        return CharacterDefinition(captured)
    except (TypeError, ValueError):
        raise ContractViolation(
            "Character", "agent_id", "must be a nonempty trimmed string",
        ) from None


def _capture(source: object, component: str, name: str) -> object:
    try:
        return getattr(source, name)
    except AttributeError:
        raise ContractViolation(component, name, "missing member") from None
    except Exception:
        raise ContractViolation(component, name, "getter failed") from None


def _entity_values(source: object, component: str, id_field: str, amount_field: str) -> tuple[str, Position, int]:
    identity = _capture(source, component, id_field)
    position = _capture(source, component, "position")
    amount = _capture(source, component, amount_field)
    try:
        _identity(identity, id_field)
    except (TypeError, ValueError):
        raise ContractViolation(component, id_field, "must be a nonempty trimmed string") from None
    try:
        # Reject foreign/subclass hooks before touching coordinates; reconstruct the
        # captured canonical value so even its nested identity is not retained.
        _exact(position, Position, "position")
        detached_position = Position(position.row, position.column)
    except (AttributeError, TypeError, ValueError):
        raise ContractViolation(component, "position", "must be a canonical Position with integer coordinates") from None
    try:
        _integer(amount, amount_field, 0)
    except (TypeError, ValueError):
        raise ContractViolation(component, amount_field, "must be a nonnegative integer") from None
    return identity, detached_position, amount


def to_artifact_definition(source: ArtifactContract) -> ArtifactDefinition:
    return ArtifactDefinition(*_entity_values(source, "Artifact", "artifact_id", "value"))


def to_enemy_definition(source: EnemyContract) -> EnemyDefinition:
    return EnemyDefinition(*_entity_values(source, "Enemy", "enemy_id", "encounter_penalty"))
