"""Exact primitive generation comparison records; not a runtime input schema."""

from __future__ import annotations

import hashlib
import json

from src.api import (
    ArtifactDefinition, CharacterDefinition, EnemyDefinition, LevelDefinition,
    LevelSpecification, PatrolDefinition, Position, Terrain, TerrainGenerationSpec,
    TerrainTopology,
)

FORMAT = "ultra-generation"
VERSION = 1


def validate_json_depth(value):
    """Keep process/replay records bounded independently of Python's JSON recursion policy."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if type(item) not in (dict, list): continue
        if depth >= 64: raise ValueError("JSON_DEPTH_LIMIT")
        children = item.values() if type(item) is dict else item
        pending.extend((child, depth + 1) for child in children if type(child) in (dict, list))


TERRAIN_SPEC_FIELDS = (
    "rows", "columns", "min_open_tiles", "max_open_tiles", "max_attempts", "topology",
)
_ERROR_CODES = frozenset({
    "INVALID_SCHEMA", "INVALID_SPECIFICATION", "INVALID_SEED", "INVALID_TERRAIN", "INVALID_LEVEL",
})
LEVEL_SPEC_FIELDS = (
    "level_id", "profile_id", "agent_id", "terrain_spec", "artifact_count", "enemy_count",
    "artifact_value_min", "artifact_value_max", "enemy_penalty_min", "enemy_penalty_max",
    "min_route_moves", "max_route_moves", "min_branch_tiles", "max_dead_end_tiles",
    "require_alternate_path", "allow_entity_overlap", "allow_entities_on_endpoints",
    "max_turns", "max_attempts",
)
LEVEL_FIELDS = ("level_id", "profile_id", "seed", "terrain", "start", "exit",
                "character", "artifacts", "enemies", "patrols")


class CanonicalError(ValueError):
    """A finite diagnostic which never includes component data or repr."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("Unknown canonical record code.")
        self._code = code
        super().__init__(code)

    @property
    def code(self) -> str:
        return self._code


def _keys(value: object, expected: tuple[str, ...]) -> dict:
    if (type(value) is not dict
            or any(type(key) is not str for key in value)
            or set(value) != set(expected)):
        raise CanonicalError("INVALID_SCHEMA")
    return value


def _envelope(record: object, kind: str, fields: tuple[str, ...]) -> dict:
    record = _keys(record, ("format", "version", "kind") + fields)
    if (type(record["format"]) is not str or record["format"] != FORMAT
            or type(record["version"]) is not int or record["version"] != VERSION
            or type(record["kind"]) is not str or record["kind"] != kind):
        raise CanonicalError("INVALID_SCHEMA")
    return record


def _record(kind: str, **fields: object) -> dict:
    return {"format": FORMAT, "version": VERSION, "kind": kind, **fields}


def _terrain_specification(specification: TerrainGenerationSpec) -> dict:
    if type(specification) is not TerrainGenerationSpec:
        raise CanonicalError("INVALID_SPECIFICATION")
    try:
        fields = {name: getattr(specification, name) for name in TERRAIN_SPEC_FIELDS}
        if not any(fields["topology"] is member for member in TerrainTopology):
            raise CanonicalError("INVALID_SPECIFICATION")
        TerrainGenerationSpec(**fields)
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_SPECIFICATION") from None
    fields["topology"] = fields["topology"].value
    return fields


def _read_terrain_specification(record: object) -> TerrainGenerationSpec:
    record = _keys(record, TERRAIN_SPEC_FIELDS)
    if (any(type(record[field]) is not int for field in TERRAIN_SPEC_FIELDS[:-1])
            or type(record["topology"]) is not str):
        raise CanonicalError("INVALID_SPECIFICATION")
    try:
        fields = dict(record)
        fields["topology"] = TerrainTopology(fields["topology"])
        return TerrainGenerationSpec(**fields)
    except (TypeError, ValueError):
        raise CanonicalError("INVALID_SPECIFICATION") from None


def _seed(seed: object) -> int:
    if type(seed) is not int or seed < 0:
        raise CanonicalError("INVALID_SEED")
    return seed


def terrain_request(specification: TerrainGenerationSpec, seed: int) -> dict:
    """Capture all six original fields and seed before any component behavior."""
    fields = _terrain_specification(specification)
    return _record("terrain-request", specification=fields, seed=_seed(seed))


def read_terrain_request(record: object) -> tuple[TerrainGenerationSpec, int]:
    """Validate primitive fields exactly and return detached public input."""
    record = _envelope(record, "terrain-request", ("specification", "seed"))
    specification = _read_terrain_specification(record["specification"])
    return specification, _seed(record["seed"])


def terrain_record(candidate: Terrain) -> dict:
    """Capture complete row-major geometry, retaining no component objects."""
    if type(candidate) is not Terrain:
        raise CanonicalError("INVALID_TERRAIN")
    try:
        owned = Terrain(candidate.terrain_rows)
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_TERRAIN") from None
    return _record("terrain", terrain_rows=list(owned.terrain_rows))


def read_terrain(record: object) -> Terrain:
    record = _envelope(record, "terrain", ("terrain_rows",))
    rows = record["terrain_rows"]
    if type(rows) is not list or any(type(row) is not str for row in rows):
        raise CanonicalError("INVALID_TERRAIN")
    try:
        return Terrain(tuple(rows))
    except (TypeError, ValueError):
        raise CanonicalError("INVALID_TERRAIN") from None


def _level_specification(specification: LevelSpecification) -> dict:
    if type(specification) is not LevelSpecification:
        raise CanonicalError("INVALID_SPECIFICATION")
    try:
        fields = {name: getattr(specification, name) for name in LEVEL_SPEC_FIELDS}
        terrain_fields = _terrain_specification(fields["terrain_spec"])
        fields["terrain_spec"] = _read_terrain_specification(terrain_fields)
        LevelSpecification(**fields)
        fields["terrain_spec"] = terrain_fields
        return fields
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_SPECIFICATION") from None


def level_request(specification: LevelSpecification, seed: int) -> dict:
    fields = _level_specification(specification)
    return _record("level-request", specification=fields, seed=_seed(seed))


def read_level_request(record: object) -> tuple[LevelSpecification, int]:
    record = _envelope(record, "level-request", ("specification", "seed"))
    fields = dict(_keys(record["specification"], LEVEL_SPEC_FIELDS))
    fields["terrain_spec"] = _read_terrain_specification(fields["terrain_spec"])
    try:
        specification = LevelSpecification(**fields)
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_SPECIFICATION") from None
    return specification, _seed(record["seed"])


def _position_record(position: Position) -> dict:
    if type(position) is not Position:
        raise CanonicalError("INVALID_LEVEL")
    try:
        row, column = position.row, position.column
        Position(row, column)
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_LEVEL") from None
    return {"row": row, "column": column}


def _read_position(record: object) -> Position:
    record = _keys(record, ("row", "column"))
    try:
        return Position(record["row"], record["column"])
    except (TypeError, ValueError):
        raise CanonicalError("INVALID_LEVEL") from None


def _array(record: object) -> list:
    if type(record) is not list:
        raise CanonicalError("INVALID_LEVEL")
    return record


def level_record(candidate: LevelDefinition) -> dict:
    """Capture every declared local field without dropping duplicate identities.

    This checks source local values only. Full original-input conformance is
    independently checked before and after capture by level_execution.
    """
    if type(candidate) is not LevelDefinition:
        raise CanonicalError("INVALID_LEVEL")
    try:
        fields = {name: getattr(candidate, name) for name in LEVEL_FIELDS}
        fields["terrain"] = terrain_record(fields["terrain"])
        fields["start"] = _position_record(fields["start"])
        fields["exit"] = _position_record(fields["exit"])
        character = fields["character"]
        if type(character) is not CharacterDefinition:
            raise CanonicalError("INVALID_LEVEL")
        fields["character"] = {"agent_id": character.agent_id}
        for name, entity_type in (("artifacts", ArtifactDefinition), ("enemies", EnemyDefinition),
                                  ("patrols", PatrolDefinition)):
            if type(fields[name]) is not tuple or any(type(x) is not entity_type for x in fields[name]):
                raise CanonicalError("INVALID_LEVEL")
        fields["artifacts"] = [dict(artifact_id=x.artifact_id, position=_position_record(x.position),
                                    value=x.value) for x in fields["artifacts"]]
        fields["enemies"] = [dict(enemy_id=x.enemy_id, position=_position_record(x.position),
                                  encounter_penalty=x.encounter_penalty) for x in fields["enemies"]]
        patrols = []
        for patrol in fields["patrols"]:
            positions = patrol.positions
            if type(positions) is not tuple:
                raise CanonicalError("INVALID_LEVEL")
            patrols.append(dict(enemy_id=patrol.enemy_id,
                                positions=[_position_record(x) for x in positions],
                                initial_phase=patrol.initial_phase))
        fields["patrols"] = patrols
        result = _record("level", **fields)
        # Prove all primitive identity/payload shapes before their sorting keys
        # are compared. Readback retains duplicates and applies no normalization.
        read_level(result)
        for name, identity in (("artifacts", "artifact_id"), ("enemies", "enemy_id"),
                               ("patrols", "enemy_id")):
            result[name].sort(key=lambda item: item[identity])
        return result
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_LEVEL") from None


def read_level(record: object) -> LevelDefinition:
    record = _envelope(record, "level", LEVEL_FIELDS)
    character = _keys(record["character"], ("agent_id",))
    artifacts, enemies, patrols = [], [], []
    try:
        for value in _array(record["artifacts"]):
            value = _keys(value, ("artifact_id", "position", "value"))
            artifacts.append(ArtifactDefinition(value["artifact_id"],
                                                _read_position(value["position"]), value["value"]))
        for value in _array(record["enemies"]):
            value = _keys(value, ("enemy_id", "position", "encounter_penalty"))
            enemies.append(EnemyDefinition(value["enemy_id"], _read_position(value["position"]),
                                          value["encounter_penalty"]))
        for value in _array(record["patrols"]):
            value = _keys(value, ("enemy_id", "positions", "initial_phase"))
            patrols.append(PatrolDefinition(enemy_id=value["enemy_id"],
                            positions=tuple(_read_position(x) for x in _array(value["positions"])),
                            initial_phase=value["initial_phase"]))
        return LevelDefinition(level_id=record["level_id"], profile_id=record["profile_id"],
                seed=record["seed"], terrain=read_terrain(record["terrain"]),
                start=_read_position(record["start"]), exit=_read_position(record["exit"]),
                character=CharacterDefinition(character["agent_id"]), artifacts=tuple(artifacts),
                enemies=tuple(enemies), patrols=tuple(patrols))
    except (AttributeError, TypeError, ValueError):
        raise CanonicalError("INVALID_LEVEL") from None


def canonical_bytes(record: object) -> bytes:
    """Encode only a validated declared schema, never arbitrary object fields."""
    if (type(record) is not dict or any(type(key) is not str for key in record)
            or type(record.get("kind")) is not str):
        raise CanonicalError("INVALID_SCHEMA")
    if record["kind"] == "terrain-request":
        owned = terrain_request(*read_terrain_request(record))
    elif record["kind"] == "terrain":
        owned = terrain_record(read_terrain(record))
    elif record["kind"] == "level-request":
        owned = level_request(*read_level_request(record))
    elif record["kind"] == "level":
        owned = level_record(read_level(record))
    else:
        raise CanonicalError("INVALID_SCHEMA")
    try:
        return json.dumps(owned, sort_keys=True, ensure_ascii=True,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise CanonicalError("INVALID_SCHEMA") from None


def digest(record: object) -> str:
    """Compact evidence identifier; comparison always uses canonical bytes."""
    return hashlib.sha256(canonical_bytes(record)).hexdigest()
