"""Versioned analytic admission for the public DEVELOPMENT straight-path family.

This rule proves L=K only for the declared entity-free geometric family. It is
neither a general solver nor an instructor certificate or course tier approval.
"""
from src.api import (CharacterDefinition, LevelDefinition, LevelSpecification,
                     Position, Terrain, TerrainGenerationSpec, TerrainTopology)
from src.framework.generation import canonical
from src.framework.level_patrol_validation import validate_level_patrol_candidate
from src.framework.generated_static.values import StaticPolicy, policy_record

CHALLENGE = "WB-INTRO-STRAIGHT-DEV"
ADMISSION_RULE = "public-straight-analytic-1"
CONFIG_FORMAT = "ultra-workbench-public-configuration"
LEVEL_FORMAT = "ultra-workbench-public-level"
VERSION = 1
POLICY = StaticPolicy("DEV-WB-INTRO-FAMILY-B", 100, 5, 20)
CONFIG_FIELDS = ("format", "version", "scope", "challenge", "axis", "length",
                 "reverse", "seed", "max_turns", "allow_wait", "policy")


class PracticeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def make_config(axis="horizontal", length=5, reverse=False, seed=1, challenge=CHALLENGE):
    """Public fixed development limits; contradictory caller values are errors."""
    value = dict(format=CONFIG_FORMAT, version=VERSION, scope="public-development",
                 challenge=challenge, axis=axis, length=length, reverse=reverse,
                 seed=seed, max_turns=16, allow_wait=True, policy=policy_record(POLICY))
    return validate_config(value)


def validate_config(value):
    if type(value) is not dict or set(value) != set(CONFIG_FIELDS):
        raise PracticeError("HOST_CONFIGURATION")
    if type(value["challenge"]) is not str or value["challenge"] != CHALLENGE:
        raise PracticeError("UNSUPPORTED_CHALLENGE")
    if (value["format"] != CONFIG_FORMAT or type(value["version"]) is not int
            or value["version"] != VERSION or value["scope"] != "public-development"
            or type(value["axis"]) is not str or value["axis"] not in ("horizontal", "vertical")
            or type(value["length"]) is not int or not 2 <= value["length"] <= 8
            or type(value["reverse"]) is not bool or type(value["seed"]) is not int
            or not 0 <= value["seed"] <= 2**31 - 1
            or type(value["max_turns"]) is not int or value["max_turns"] != 16
            or value["max_turns"] < value["length"] or value["allow_wait"] is not True
            or value["policy"] != policy_record(POLICY)):
        raise PracticeError("HOST_CONFIGURATION")
    # JSON equality alone permits bool/int aliases; canonical byte equality does not.
    from src.framework.static_records import encode
    if encode(value["policy"]) != encode(policy_record(POLICY)):
        raise PracticeError("HOST_CONFIGURATION")
    return dict(value, policy=policy_record(POLICY))


def public_request(config):
    config = validate_config(config)
    k = config["length"]
    rows, columns = (1, k) if config["axis"] == "horizontal" else (k, 1)
    terrain = TerrainGenerationSpec(rows=rows, columns=columns, min_open_tiles=k,
        max_open_tiles=k, max_attempts=3, topology=TerrainTopology.STRAIGHT_PATH)
    spec = LevelSpecification(level_id="wb-intro", profile_id=CHALLENGE, agent_id="explorer",
        terrain_spec=terrain, artifact_count=0, enemy_count=0, artifact_value_min=0,
        artifact_value_max=0, enemy_penalty_min=0, enemy_penalty_max=0,
        min_route_moves=k-1, max_route_moves=k-1, min_branch_tiles=0,
        max_dead_end_tiles=2, require_alternate_path=False, allow_entity_overlap=False,
        allow_entities_on_endpoints=False, max_turns=config["max_turns"], max_attempts=3)
    return spec, config["seed"]


def admit_public(level, config):
    """Capture canonical fields and prove all assumptions before deriving baseline."""
    config = validate_config(config)
    spec, seed = public_request(config)
    try:
        validate_level_patrol_candidate(level, spec, seed, provenance="student-static")
        record = canonical.level_record(level)
        owned = canonical.read_level(record)
        validate_level_patrol_candidate(owned, spec, seed, provenance="student-static")
        cells = [(r, c) for r, row in enumerate(owned.terrain.terrain_rows)
                 for c, symbol in enumerate(row) if symbol == "."]
        k = config["length"]
        expected = [(0, c) for c in range(k)] if config["axis"] == "horizontal" else [(r, 0) for r in range(k)]
        start, exit = (owned.start.row, owned.start.column), (owned.exit.row, owned.exit.column)
        if (cells != expected or len(cells) != k or k < 2
                or {start, exit} != {expected[0], expected[-1]} or start == exit or owned.artifacts or owned.enemies
                or owned.patrols or owned.seed != seed or owned.level_id != spec.level_id
                or owned.profile_id != spec.profile_id or owned.character.agent_id != spec.agent_id):
            raise PracticeError("INVALID_PUBLIC_CANDIDATE")
        # The supplied topology validator independently proves connectivity and the
        # straight path. Endpoints at its ends force K-1 moves plus explicit EXIT.
        return owned, spec, k
    except PracticeError:
        raise
    except Exception:
        raise PracticeError("INVALID_PUBLIC_CANDIDATE") from None


def public_level_record(level, config):
    owned, _, baseline = admit_public(level, config)
    return dict(format=LEVEL_FORMAT, version=VERSION, scope="public-development",
                configuration=validate_config(config), level=canonical.level_record(owned),
                admission_rule=ADMISSION_RULE, baseline_cost=baseline)


def read_public_level(value):
    if (type(value) is not dict or set(value) != {"format", "version", "scope", "configuration",
            "level", "admission_rule", "baseline_cost"} or value["format"] != LEVEL_FORMAT
            or type(value["version"]) is not int or value["version"] != VERSION
            or value["scope"] != "public-development" or value["admission_rule"] != ADMISSION_RULE):
        raise PracticeError("INVALID_PUBLIC_LEVEL")
    try:
        level = canonical.read_level(value["level"])
        expected = public_level_record(level, value["configuration"])
        from src.framework.static_records import encode
        if encode(expected) != encode(value):
            raise PracticeError("INVALID_PUBLIC_LEVEL")
        return level, validate_config(value["configuration"])
    except PracticeError:
        raise
    except Exception:
        raise PracticeError("INVALID_PUBLIC_LEVEL") from None


def fixed_public_level(config=None):
    """A published input for controller-only practice; generation uses student code."""
    config = make_config() if config is None else validate_config(config)
    spec, seed = public_request(config)
    k = config["length"]
    rows = ("." * k,) if config["axis"] == "horizontal" else (".",) * k
    last = Position(0, k-1) if config["axis"] == "horizontal" else Position(k-1, 0)
    start, exit = (last, Position(0, 0)) if config["reverse"] else (Position(0, 0), last)
    return LevelDefinition(level_id=spec.level_id, profile_id=spec.profile_id, seed=seed,
        terrain=Terrain(rows), start=start, exit=exit, character=CharacterDefinition(spec.agent_id),
        artifacts=(), enemies=(), patrols=())
