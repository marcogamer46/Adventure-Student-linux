"""CLI-first Algorithmic Expedition public development workbench."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import uuid
from src.framework.public_practice.admission import (CHALLENGE, PracticeError, make_config,
                                                    read_public_level)
from src.framework.public_practice.records import validate_public_record
from src.framework.static_records import encode, read_json, ReplayError

ROOT = Path(__file__).resolve().parents[2]
MAX_INPUT = 1048576


def bounded(path, *, limit=MAX_INPUT):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise PracticeError("INPUT_LIMIT")
    return raw


def destination(value, workspace, *, directory=False):
    """Writes belong only to a fresh selected-workspace practice destination."""
    workspace = Path(workspace).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = workspace / path
    intended = workspace / "practice"
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if (current.is_symlink() or getattr(current, "is_junction", lambda: False)()
                or (current.exists() and current.lstat().st_file_attributes & 1024 if os.name == "nt" else False)):
            raise PracticeError("OUTPUT_PATH_ESCAPE")
    path = path.resolve()
    if not path.is_relative_to(intended) or path == intended:
        raise PracticeError("OUTPUT_OUTSIDE_PRACTICE")
    if path.exists():
        raise PracticeError("OUTPUT_EXISTS")
    if not directory and path.suffix.lower() != ".json":
        raise PracticeError("OUTPUT_REQUIRES_JSON")
    return path


def reserve(path, *, directory=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if directory:
        path.mkdir()
        marker = path / "attempt.json"
    else:
        marker = path
    with marker.open("xb") as stream:
        stream.write(encode(dict(status="INCOMPLETE", code="ATTEMPT_STARTED")))


def atomic(path, raw):
    pending = path.with_name(path.name + ".pending-" + uuid.uuid4().hex)
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def doctor(workspace):
    # Presence checks import no student, Tk, Pillow, simulator or worker.
    import src.api
    from src.framework.submission.identity import ENTRIES
    gui = dict(tk_available=importlib.util.find_spec("tkinter") is not None,
               pillow_available=importlib.util.find_spec("PIL") is not None,
               assets_present=(ROOT / "assets/presentation/asset-manifest-v2.json").is_file())
    supported = platform.python_implementation() == "CPython" and platform.python_version() == "3.12.14"
    return dict(status="OK" if supported else "HOST_UNSUPPORTED", scope="public-development",
                python=platform.python_version(), tested_python="3.12.14", core_available=supported,
                api_version=src.api.API_VERSION, api_exports=len(src.api.__all__),
                entry_files={name: (workspace / path).is_file() for name, path in ENTRIES.items()},
                code_readiness="NOT_EXECUTED", student_code_executed=False, gui=gui)


def show(raw, *, headless=False, demo=False):
    view = validate_public_record(raw)
    data = read_json(raw)
    if headless:
        return dict(status="OK", scope="public-development", demonstration=demo,
                    student_code_executed=False, source_identity=data["source_identity"]["sha256"],
                    frames=len(view.snapshots), result=view.summary, authority="LOCAL_CONSISTENCY_ONLY_NO_GRADE")
    if importlib.util.find_spec("PIL") is None:
        raise PracticeError("VIEWER_PILLOW_REQUIRED")
    from src.renderer.expedition.practice import load_public
    from src.renderer.expedition.view import ExpeditionViewer, ViewerUnavailableError
    try:
        recording = load_public(raw, title="Bundled demonstration" if demo else "Saved public practice")
        ExpeditionViewer({"practice": recording}, selected="practice",
            asset_manifest=ROOT / "assets/presentation/asset-manifest-v2.json", public_showcase=False).run()
    except ViewerUnavailableError:
        raise PracticeError("VIEWER_UNAVAILABLE") from None
    return dict(status="OK", demonstration=demo, student_code_executed=False)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, default=ROOT, help="Explicit student workspace; defaults to package root")
    p.add_argument("--details", action="store_true", help="Include full public diagnostics")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("doctor", "demo"):
        item = sub.add_parser(name)
        item.add_argument("--headless", action="store_true")
    sub.add_parser("check")
    sub.add_parser("challenges", help="List every public project family; no tier unlocks")
    description = sub.add_parser("describe")
    description.add_argument("--challenge", required=True)
    example = sub.add_parser("example", help="Prepare an independent public controller input")
    example.add_argument("--challenge", required=True)
    example.add_argument("--seed", type=int, default=0)
    example.add_argument("--config", help="JSON object containing published configuration overrides")
    example.add_argument("--output", required=True)
    diagnostic = sub.add_parser("diagnose", help="Run independent public diagnostic cases on one source revision")
    diagnostic.add_argument("--tier", type=int, choices=range(9))
    diagnostic.add_argument("--output", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--challenge", default=CHALLENGE)
    gen.add_argument("--seed", type=int, required=True)
    gen.add_argument("--axis", choices=("horizontal", "vertical"), default="horizontal")
    gen.add_argument("--length", type=int, default=5)
    gen.add_argument("--reverse", action="store_true", help="Fixed input selection hint; generated end order is student-owned")
    gen.add_argument("--output", required=True)
    gen.add_argument("--kind", choices=("terrain", "level"), default="level")
    gen.add_argument("--dependency", choices=("student", "reference"), default="student")
    gen.add_argument("--config", help="JSON object containing published configuration overrides")
    val = sub.add_parser("validate"); val.add_argument("--level", required=True)
    solve = sub.add_parser("solve"); solve.add_argument("--level", required=True); solve.add_argument("--output", required=True)
    replay = sub.add_parser("replay"); replay.add_argument("--run", required=True); replay.add_argument("--headless", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    workspace = args.workspace.resolve()
    command = args.command
    reserved = None
    try:
        project_command = command in {"challenges", "describe", "example", "diagnose"}
        if command == "generate":
            project_command = args.challenge != CHALLENGE
        elif command in {"validate", "solve"}:
            selected_input = read_json(bounded(args.level, limit=16 * 1024 * 1024))
            project_command = type(selected_input) is dict and selected_input.get("format") == "ultra-public-project-level"
        elif command == "replay":
            selected_input = read_json(bounded(Path(args.run) / "run.json", limit=16 * 1024 * 1024))
            project_command = type(selected_input) is dict and selected_input.get("format") == "ultra-public-project-run"
        if project_command:
            from .project import dispatch
            selected = dispatch(args, workspace, bounded=lambda path: bounded(path, limit=16 * 1024 * 1024), destination=destination,
                                reserve=reserve, atomic=atomic)
            if selected is not None:
                result, code = selected
                if not args.details:
                    result.pop("worker", None)
                print(json.dumps(result, sort_keys=True, ensure_ascii=True))
                return code
        if command == "doctor":
            result = doctor(workspace); code = 0 if result["core_available"] else 2
        elif command == "demo":
            result = show(bounded(ROOT / "demos/workbench/intro-run.json"), headless=args.headless, demo=True); code = 0
        elif command == "validate":
            level, config = read_public_level(read_json(bounded(args.level)))
            result = dict(status="OK", challenge=config["challenge"], baseline_cost=config["length"],
                          student_code_executed=False, authority="PUBLIC_ANALYTIC_DEVELOPMENT"); code = 0
        elif command == "replay":
            folder = Path(args.run)
            raw = bounded(folder / "run.json")
            validate_public_record(raw)
            manifest = read_json(bounded(folder / "manifest.json"))
            data = read_json(raw)
            if (type(manifest) is not dict or set(manifest) != {"format", "version", "status", "run_id", "recorded_utc",
                    "run_sha256", "source_identity", "runtime_identity", "python", "challenge",
                    "generation_source_identity", "authority"}
                    or manifest["format"] != "ultra-workbench-local-manifest"
                    or type(manifest["version"]) is not int or manifest["version"] != 1
                    or manifest["run_sha256"] != hashlib.sha256(raw).hexdigest() or manifest["status"] != "SAVED"
                    or type(data) is not dict
                    or manifest["source_identity"] != data.get("source_identity", {}).get("sha256")
                    or manifest["runtime_identity"] != data.get("runtime_identity", {}).get("sha256")
                    or manifest["challenge"] != CHALLENGE or manifest["authority"] != "LOCAL_PUBLIC_PRACTICE_NO_GRADE"):
                raise PracticeError("RUN_MANIFEST_MISMATCH")
            result = show(raw, headless=args.headless); code = 0
        else:
            # Passive commands above never import execution workers or source loader.
            from .process import execute, WorkbenchError, runtime_identity, source_identity
            from src.framework.submission.identity import capture_sources, ENTRIES, verify_sources
            if command == "check":
                manifest = capture_sources(workspace)
                outcomes = []
                for component, relative in ENTRIES.items():
                    if not (workspace / relative).is_file():
                        outcomes.append(dict(component=component, status="INCOMPLETE", code="MISSING_COMPONENT")); continue
                    try:
                        item = execute("probe", workspace, dict(component=component), manifest=manifest)
                        item.pop("worker", None)
                        outcomes.append(item)
                    except WorkbenchError as exc:
                        outcomes.append(dict(component=component, status=exc.status, code=exc.code))
                complete = all(item["status"] == "OK" for item in outcomes)
                result = dict(status="SHAPES_VERIFIED" if complete else "INCOMPLETE", components=outcomes,
                    next_step="Implement the named TODO or contract, then generate or solve the fixed public input.",
                    whole_package_behavior="NOT_CERTIFIED", tier_awarded=False); code = 0 if complete else 1
            elif command == "generate":
                config = make_config(args.axis, args.length, args.reverse, args.seed, args.challenge)
                path = destination(args.output, workspace)
                provenance_path = destination(str(path) + ".manifest.json", workspace)
                reserve(path); reserved = path
                manifest = capture_sources(workspace)
                runtime = runtime_identity()
                outcome = execute("generate", workspace, dict(configuration=config), manifest=manifest, runtime=runtime)
                read_public_level(outcome["level"])
                raw = encode(outcome["level"])
                atomic(path, raw)
                with provenance_path.open("xb") as stream:
                    stream.write(encode(dict(format="ultra-workbench-generation-provenance", version=1,
                        level_sha256=hashlib.sha256(raw).hexdigest(), source_identity=source_identity(manifest),
                        runtime_identity=runtime, authority="LOCAL_PUBLIC_CONTENT_BINDING_ONLY")))
                result = dict(status="OK", level=str(path), challenge=CHALLENGE,
                              generation_source_identity=source_identity(manifest)["sha256"],
                              provenance=str(provenance_path), terrain_calls=outcome["terrain_calls"], worker=outcome["worker"]); code = 0
            elif command == "solve":
                path = destination(args.output, workspace, directory=True)
                level_data = read_json(bounded(args.level))
                read_public_level(level_data)  # Admission precedes any student execution.
                generation_source = None
                provenance_path = Path(str(args.level) + ".manifest.json")
                if provenance_path.exists():
                    provenance = read_json(bounded(provenance_path))
                    from src.framework.public_practice.records import validate_identity
                    if (type(provenance) is not dict or set(provenance) != {"format", "version", "level_sha256",
                            "source_identity", "runtime_identity", "authority"}
                            or provenance["format"] != "ultra-workbench-generation-provenance"
                            or type(provenance["version"]) is not int or provenance["version"] != 1
                            or provenance["level_sha256"] != hashlib.sha256(encode(level_data)).hexdigest()
                            or provenance["authority"] != "LOCAL_PUBLIC_CONTENT_BINDING_ONLY"):
                        raise PracticeError("GENERATION_PROVENANCE_MISMATCH")
                    generation_source = validate_identity(provenance["source_identity"])["sha256"]
                    validate_identity(provenance["runtime_identity"])
                reserve(path, directory=True); reserved = path / "attempt.json"
                manifest = capture_sources(workspace)
                runtime = runtime_identity()
                outcome = execute("solve", workspace, dict(level=level_data), manifest=manifest, runtime=runtime)
                raw = encode(outcome["run"])
                view = validate_public_record(raw)
                verify_sources(workspace, manifest)
                atomic(path / "level.json", encode(level_data))
                atomic(path / "run.json", raw)
                tracking = dict(format="ultra-workbench-local-manifest", version=1, status="SAVED",
                    run_id=uuid.uuid4().hex, recorded_utc=datetime.now(timezone.utc).isoformat(),
                    run_sha256=hashlib.sha256(raw).hexdigest(), source_identity=source_identity(manifest)["sha256"],
                    runtime_identity=runtime["sha256"], python=platform.python_version(), challenge=CHALLENGE,
                    generation_source_identity=generation_source,
                    authority="LOCAL_PUBLIC_PRACTICE_NO_GRADE")
                atomic(path / "manifest.json", encode(tracking))
                atomic(reserved, encode(dict(status="SAVED", outcome=outcome["outcome"], code=outcome["code"])))
                result = dict(status="COMPLETED" if view.summary["completed"] else "FAILED_RUN_SAVED",
                    outcome=outcome["outcome"], code=outcome["code"], run=str(path),
                    source_identity=tracking["source_identity"], metrics=view.summary,
                    whole_package_readiness="NOT_ASSESSED", tier_awarded=False, worker=outcome["worker"])
                code = 0 if view.summary["completed"] else 1
        if not args.details:
            result.pop("worker", None)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return code
    except (PracticeError, ReplayError, OSError, ValueError) as exc:
        error_code = getattr(exc, "code", "INPUT_OR_HOST_ERROR")
        status = getattr(exc, "status", "REJECTED")
        result = dict(status=status, code=error_code, scope="public-development",
                      next_step="Fix the named input/component or choose a fresh practice output; no previous success is reused.")
        if reserved is not None:
            atomic(reserved, encode(result))
        print(json.dumps(result, sort_keys=True))
        return 1 if status in {"INCOMPLETE", "CONFORMANCE_FAILURE", "CONTRACT_FAILURE", "IMPORT_FAILURE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
