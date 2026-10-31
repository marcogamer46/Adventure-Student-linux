"""Data-only public v2 admission and history verification.

An exact minimum is checked from a saved upper-bound witness and closed
lower-bound labels. This module performs no search, execution or source import.
Public derived proof data is consistency evidence, not instructor certification.
"""
import hashlib
from src.api import WorldAction, WorldActionType
from src.framework.generation import canonical
from src.framework.static_records import (MAX_RECORD_BYTES, ReplayError, _keys,
    encode, read_json, validate_history as validate_static_history)
from src.framework.public_practice.records import validate_identity
from src.framework.generated_static.values import StaticPolicy, policy_record
from src.framework.patrol_values import PatrolPolicy, policy_record as patrol_policy_record
from src.framework.baseline.static.values import StaticCertificate
from src.framework.baseline.static.proof import verify_certificate as verify_static
from src.framework.baseline.patrol.values import PatrolCertificate, PatrolRules, encode_rules
from src.framework.baseline.patrol.proof import verify_certificate as verify_patrol
from src.framework.patrol_records import validate_history as validate_patrol_history

LEVEL_FORMAT = "ultra-public-project-level"
RUN_FORMAT = "ultra-public-project-run"
VERSION = 2
SCOPE = "public-development"
LEVEL_FIELDS = ("format", "version", "scope", "configuration", "level", "request",
                "rules", "policy", "baseline_cost", "proof")
RUN_FIELDS = ("format", "version", "scope", "development_only", "admission",
              "source_identity", "runtime_identity", "generation_identity", "events", "frames", "summary")
PROOF_FIELDS = ("format", "version", "mode", "rules_version", "algorithm_version",
                "level_sha256", "request_sha256", "rules_sha256", "baseline_cost", "labels", "witness")


def gameplay(config):
    """Translate the frozen catalog policy to the existing Family B engine."""
    values = config["policy"]
    patrol = config["rules"]["mode"] == "patrol"
    policy = (PatrolPolicy if patrol else StaticPolicy)(values["policy_id"], values["B"], values["r"], values["Q"])
    rules = dict(allow_wait=config["rules"]["allow_wait"], allow_collect=True,
                 allow_engage=True, deadline_turn=config["rules"]["D"])
    return policy, (patrol_policy_record if patrol else policy_record)(policy), rules


def proof_record(certificate, mode, rules):
    return dict(format="ultra-public-minimum-proof", version=VERSION, mode=mode,
        rules_version=certificate.rules_version, algorithm_version=certificate.algorithm_version,
        level_sha256=hashlib.sha256(certificate.level_bytes).hexdigest(),
        request_sha256=hashlib.sha256(certificate.request_bytes).hexdigest(),
        rules_sha256=hashlib.sha256(encode(rules)).hexdigest(), baseline_cost=certificate.baseline_cost,
        labels=[list(label) for label in certificate.labels], witness=[
            dict(action_type=action.action_type.value, target_id=action.target_id) for action in certificate.witness])


def read_level(value):
    """Rebuild an owned level and verify the saved exact-minimum proof passively."""
    from .catalog import validate_configuration, request, validate_family_endpoints
    value = _keys(value, LEVEL_FIELDS)
    if (value["format"] != LEVEL_FORMAT or type(value["version"]) is not int
            or value["version"] != VERSION or value["scope"] != SCOPE):
        raise ReplayError("UNSUPPORTED_PUBLIC_VERSION")
    try:
        config = validate_configuration(value["configuration"])
        spec, seed = request(config)
        level = canonical.read_level(value["level"])
        validate_family_endpoints(level, config["tier"])
        policy, pd, rules = gameplay(config)
        if (encode(value["request"]) != encode(canonical.level_request(spec, seed))
                or encode(value["level"]) != encode(canonical.level_record(level))
                or encode(value["rules"]) != encode(rules) or encode(value["policy"]) != encode(pd)
                or type(value["baseline_cost"]) is not int or value["baseline_cost"] < 1):
            raise ReplayError("PUBLIC_ADMISSION_MISMATCH")
        p = _keys(value["proof"], PROOF_FIELDS)
        if (p["format"] != "ultra-public-minimum-proof" or type(p["version"]) is not int
                or p["version"] != VERSION or p["mode"] != config["rules"]["mode"]
                or type(p["labels"]) is not list or not 1 <= len(p["labels"]) <= 250000
                or type(p["witness"]) is not list or not 1 <= len(p["witness"]) <= spec.max_turns
                or type(p["baseline_cost"]) is not int or p["baseline_cost"] != value["baseline_cost"]):
            raise ReplayError("INVALID_PUBLIC_PROOF")
        labels = tuple(tuple(row) if type(row) is list else row for row in p["labels"])
        witness = []
        for action in p["witness"]:
            action = _keys(action, ("action_type", "target_id"))
            if type(action["action_type"]) is not str or (action["target_id"] is not None and type(action["target_id"]) is not str):
                raise ReplayError("INVALID_PUBLIC_PROOF")
            witness.append(WorldAction(WorldActionType(action["action_type"]), target_id=action["target_id"]))
        lb, rb = canonical.canonical_bytes(value["level"]), canonical.canonical_bytes(value["request"])
        if p["mode"] == "static":
            certificate = StaticCertificate(lb, rb, rules["allow_wait"], p["baseline_cost"],
                tuple(witness), labels, p["rules_version"], p["algorithm_version"])
            valid = verify_static(certificate, level)
        else:
            timing = PatrolRules(**rules)
            certificate = PatrolCertificate(lb, rb, encode_rules(timing, spec.max_turns), p["baseline_cost"],
                tuple(witness), labels, p["rules_version"], p["algorithm_version"])
            valid = verify_patrol(certificate, level, spec, seed, timing)
        if not valid or encode(p) != encode(proof_record(certificate, p["mode"], rules)):
            raise ReplayError("INVALID_PUBLIC_PROOF")
        return level, config, value
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("INVALID_PUBLIC_ADMISSION") from None


def seal_record(admission, events, frames, summary, source_identity, runtime_identity, generation_identity=None):
    value = dict(format=RUN_FORMAT, version=VERSION, scope=SCOPE, development_only=True,
        admission=admission, source_identity=validate_identity(source_identity),
        runtime_identity=validate_identity(runtime_identity),
        generation_identity=None if generation_identity is None else validate_identity(generation_identity),
        events=events, frames=frames, summary=summary)
    raw = encode(value)
    if len(raw) > MAX_RECORD_BYTES:
        raise ReplayError("RECORD_LIMIT")
    return raw, None


def validate_record(raw):
    record = _keys(read_json(raw), RUN_FIELDS)
    if (record["format"] != RUN_FORMAT or type(record["version"]) is not int
            or record["version"] != VERSION or record["scope"] != SCOPE or record["development_only"] is not True):
        raise ReplayError("UNSUPPORTED_PUBLIC_VERSION")
    validate_identity(record["source_identity"])
    validate_identity(record["runtime_identity"])
    if record["generation_identity"] is not None:
        validate_identity(record["generation_identity"])
    level, config, admission = read_level(record["admission"])
    policy, _, rules = gameplay(config)
    if config["rules"]["mode"] == "static":
        return validate_static_history(record, level, policy, admission["baseline_cost"], config["rules"]["H"], rules["allow_wait"])
    return validate_patrol_history(record, level, policy, admission["baseline_cost"], config["rules"]["H"], rules)


def load_replay(path):
    try:
        with open(path, "rb") as stream:
            return validate_record(stream.read(MAX_RECORD_BYTES + 1))
    except OSError:
        raise ReplayError("REPLAY_IO_ERROR") from None
