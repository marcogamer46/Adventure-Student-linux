"""Strict passive public practice validation; never imports execution machinery.

Self-consistent local data establishes public development consistency only.
Digests establish content identity, not authorship, authenticity or a grade.
"""
import hashlib
from pathlib import PurePosixPath
from src.framework.generation import canonical
from src.framework.static_records import (MAX_RECORD_BYTES, ReplayError, ReplayView,
    _keys, encode, read_json, validate_history)
from .admission import (ADMISSION_RULE, CHALLENGE, POLICY, VERSION, PracticeError,
                        admit_public, public_request, validate_config)

RUN_FORMAT = "ultra-workbench-public-run"
RUN_FIELDS = ("format", "version", "scope", "development_only", "admission",
              "source_identity", "runtime_identity", "events", "frames", "summary")


def validate_identity(value):
    value = _keys(value, ("sha256", "files"))
    files = value["files"]
    def sha(item):
        return type(item) is str and len(item) == 64 and all(c in "0123456789abcdef" for c in item)
    if not sha(value["sha256"]) or type(files) is not dict or not 1 <= len(files) <= 10000:
        raise ReplayError("INVALID_CONTENT_IDENTITY")
    for path, digest in files.items():
        if (type(path) is not str or not path or len(path) > 512 or "\\" in path or ":" in path
                or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
                or PurePosixPath(path).as_posix() != path or not sha(digest)):
            raise ReplayError("INVALID_CONTENT_IDENTITY")
    if hashlib.sha256(encode(files)).hexdigest() != value["sha256"]:
        raise ReplayError("CONTENT_IDENTITY_MISMATCH")
    return dict(sha256=value["sha256"], files=dict(files))


def identity_from_files(files):
    return validate_identity(dict(files=dict(files), sha256=hashlib.sha256(encode(files)).hexdigest()))


def admission_record(level, config):
    config = validate_config(config)
    owned, spec, baseline = admit_public(level, config)
    return dict(configuration=config, challenge=CHALLENGE, level=canonical.level_record(owned),
                request=canonical.level_request(spec, config["seed"]),
                rule=ADMISSION_RULE, baseline_cost=baseline)


def seal_public_record(admission, events, frames, summary, source_identity, runtime_identity):
    record = dict(format=RUN_FORMAT, version=VERSION, scope="public-development", development_only=True,
        admission=admission, source_identity=validate_identity(source_identity),
        runtime_identity=validate_identity(runtime_identity), events=events, frames=frames, summary=summary)
    raw = encode(record)
    if len(raw) > MAX_RECORD_BYTES:
        raise ReplayError("RECORD_LIMIT")
    return raw, None


def validate_public_record(raw):
    record = _keys(read_json(raw), RUN_FIELDS)
    if (record["format"] != RUN_FORMAT or type(record["version"]) is not int
            or record["version"] != VERSION or record["scope"] != "public-development"
            or record["development_only"] is not True):
        raise ReplayError("UNSUPPORTED_PUBLIC_VERSION")
    validate_identity(record["source_identity"])
    validate_identity(record["runtime_identity"])
    admission = _keys(record["admission"], ("configuration", "challenge", "level", "request", "rule", "baseline_cost"))
    try:
        config = validate_config(admission["configuration"])
        level = canonical.read_level(admission["level"])
        owned, spec, baseline = admit_public(level, config)
        expected = admission_record(owned, config)
        if encode(expected) != encode(admission):
            raise ReplayError("PUBLIC_ADMISSION_MISMATCH")
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("INVALID_PUBLIC_ADMISSION") from None
    return validate_history(record, owned, POLICY, baseline, spec.max_turns, config["allow_wait"])


def load_public_record(path):
    try:
        with open(path, "rb") as stream:
            return validate_public_record(stream.read(MAX_RECORD_BYTES + 1))
    except OSError:
        raise ReplayError("REPLAY_IO_ERROR") from None
