"""Format-neutral source bindings and finite local process cleanup.

These content checks do not authenticate authorship or provide OS containment.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
from src.api import API_VERSION

ROOT = Path(__file__).resolve().parents[2]


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("MALFORMED_RECORD")
    return value


def sha(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("MALFORMED_DIGEST")
    return value


def tree_identity(root, directories):
    root = Path(root).resolve()
    return digest({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for directory in directories for p in sorted((root / directory).rglob("*.py"))})


def contract_identity(root=ROOT):
    return dict(api_version=API_VERSION, sha256=tree_identity(root, ("src/api",)))


def terminate(process):
    """Reap only the process group created by the caller (historical behavior)."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
