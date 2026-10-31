"""Contained source inventories, exact bytes, and revision drift checks."""
import hashlib
import os
from pathlib import Path, PurePosixPath
from src.framework.source_support import contract_identity, canonical_bytes, digest, keys, sha

ENTRIES = {
    "Character": "src/student/character.py",
    "Artifact": "src/student/artifact.py",
    "Enemy": "src/student/enemy.py",
    "AgentController": "src/student/controller.py",
    "TerrainGenerator": "src/student/terrain_generator.py",
    "LevelGenerator": "src/student/level_generator.py",
}
MAX_FILES = 256
MAX_SOURCE_BYTES = 4 * 1024 * 1024


class SubmissionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_paths(paths):
    seen = set()
    for relative in paths:
        if type(relative) is not str or not relative or "\\" in relative or ":" in relative:
            raise SubmissionError("PATH_ESCAPE")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "." in path.parts or str(path) != relative:
            raise SubmissionError("PATH_ESCAPE")
        if relative != "src/__init__.py" and not relative.startswith("src/student/"):
            raise SubmissionError("PATH_ESCAPE")
        folded = relative.casefold()
        if folded in seen:
            raise SubmissionError("CASEFOLD_COLLISION")
        seen.add(folded)


def contained(root, relative):
    validate_paths([relative])
    root = Path(root).resolve()
    path = root / relative
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise SubmissionError("PATH_ESCAPE")
        if not current.resolve().is_relative_to(root):
            raise SubmissionError("PATH_ESCAPE")
    return path


def _exact_child(parent, spelling):
    matches = [p for p in parent.iterdir() if p.name.casefold() == spelling.casefold()]
    if len(matches) > 1:
        raise SubmissionError("CASEFOLD_COLLISION")
    return matches[0] if matches and matches[0].name == spelling else None


def capture_sources(root, *, contract=None):
    """Scan only the explicitly selected src/student tree and src package marker.

    All helper/data bytes in that tree are pinned, even if a particular probe does
    not import them. Bytecode caches are ignored and never used by the loader.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise SubmissionError("MISSING_SUBMISSION_ROOT")
    sources = []
    total = 0
    def add(path):
        nonlocal total
        relative = path.relative_to(root).as_posix()
        path = contained(root, relative)
        size = path.stat().st_size
        if size > MAX_SOURCE_BYTES or len(sources) >= MAX_FILES:
            raise SubmissionError("SOURCE_LIMIT")
        data = path.read_bytes(); total += len(data)
        if total > MAX_SOURCE_BYTES:
            raise SubmissionError("SOURCE_LIMIT")
        sources.append(dict(path=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    src = _exact_child(root, "src")
    if src is not None:
        if not src.is_dir(): raise SubmissionError("UNSUPPORTED_SOURCE")
        contained(root, "src/__init__.py")
        marker = _exact_child(src, "__init__.py")
        if marker is not None and marker.is_file(): add(marker)
        student = _exact_child(src, "student")
        if student is not None:
            if not student.is_dir(): raise SubmissionError("UNSUPPORTED_SOURCE")
            contained(root, "src/student/__init__.py")
            visited = 0
            def walk(directory, depth=0):
                nonlocal visited
                if depth > 16: raise SubmissionError("SOURCE_LIMIT")
                children = sorted(directory.iterdir(), key=lambda p: p.name)
                visited += len(children)
                if visited > 512: raise SubmissionError("SOURCE_LIMIT")
                names = [p.name.casefold() for p in children]
                if len(names) != len(set(names)):
                    raise SubmissionError("CASEFOLD_COLLISION")
                for path in children:
                    if path.name == "__pycache__": continue
                    relative = path.relative_to(root).as_posix()
                    contained(root, relative)
                    if path.is_dir(): walk(path, depth + 1)
                    elif path.is_file():
                        if path.suffix in (".pyc", ".pyo", ".pyd", ".so", ".zip"):
                            raise SubmissionError("UNSUPPORTED_HELPER_FORMAT")
                        add(path)
                    else: raise SubmissionError("UNSUPPORTED_SOURCE")
            walk(student)
    validate_paths([item["path"] for item in sources])
    return dict(format="ultra-submission-sources", version=1, contract=contract or contract_identity(),
                root_manifest="explicit-root/src/student", sources=sorted(sources, key=lambda p: p["path"]))


def read_manifest(value):
    try:
        keys(value, ("format", "version", "contract", "root_manifest", "sources"))
        if (value["format"] != "ultra-submission-sources" or type(value["version"]) is not int or value["version"] != 1
                or value["root_manifest"] != "explicit-root/src/student"):
            raise SubmissionError("MALFORMED_SOURCE_MANIFEST")
        if type(value["sources"]) is not list or len(value["sources"]) > MAX_FILES:
            raise SubmissionError("SOURCE_LIMIT")
        total = 0
        for item in value["sources"]:
            keys(item, ("path", "bytes", "sha256")); sha(item["sha256"])
            if type(item["bytes"]) is not int or item["bytes"] < 0:
                raise SubmissionError("MALFORMED_SOURCE_MANIFEST")
            total += item["bytes"]
        if total > MAX_SOURCE_BYTES: raise SubmissionError("SOURCE_LIMIT")
        validate_paths([item["path"] for item in value["sources"]])
        keys(value["contract"], ("api_version", "sha256")); sha(value["contract"]["sha256"])
        return value
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, SubmissionError): raise
        raise SubmissionError("MALFORMED_SOURCE_MANIFEST") from None


def verify_sources(root, manifest):
    read_manifest(manifest)
    try:
        current = capture_sources(root, contract=manifest["contract"])
        if canonical_bytes(current) != canonical_bytes(manifest):
            raise SubmissionError("SOURCE_DRIFT")
    except (OSError, SubmissionError):
        raise SubmissionError("SOURCE_DRIFT") from None


def source_bytes(root, manifest, relative):
    read_manifest(manifest)
    item = next((s for s in manifest["sources"] if s["path"] == relative), None)
    if item is None:
        raise SubmissionError("UNSELECTED_SOURCE")
    try:
        raw = contained(Path(root).resolve(), relative).read_bytes()
    except OSError:
        raise SubmissionError("SOURCE_DRIFT") from None
    if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise SubmissionError("SOURCE_DRIFT")
    return raw


def component_descriptor(manifest, component):
    read_manifest(manifest)
    if component not in ENTRIES: raise SubmissionError("UNKNOWN_COMPONENT")
    path = ENTRIES[component]
    item = next((s for s in manifest["sources"] if s["path"] == path), None)
    if item is None: raise SubmissionError("MISSING_COMPONENT")
    return dict(path=path, symbol=component, sha256=item["sha256"], submission=manifest)
