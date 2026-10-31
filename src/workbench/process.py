"""Fresh cooperative student workers with finite output/time/source controls."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from src.framework.source_support import terminate
from src.framework.submission.identity import (ENTRIES, capture_sources, verify_sources,
                                               source_bytes, SubmissionError)
from src.framework.public_practice.records import identity_from_files
from src.framework.static_records import encode, read_json

ROOT = Path(__file__).resolve().parents[2]
LIMITS = dict(import_seconds=5, generation_seconds=5, controller_seconds=10,
              output_bytes=65536, result_bytes=1048576, temporary_bytes=2097152,
              temporary_files=16, source_bytes=4194304, source_files=256)


class WorkbenchError(ValueError):
    def __init__(self, code, status="INCOMPLETE", resources=None, diagnostic=None):
        self.code, self.status = code, status
        self.resources = resources
        self.diagnostic = diagnostic
        super().__init__(code)


def source_identity(manifest):
    return identity_from_files({p["path"]: p["sha256"] for p in manifest["sources"]})


def runtime_identity(root=ROOT, *, project=False, gui=False):
    from .runtime_files import PUBLIC_RUNTIME_FILES, PROJECT_RUNTIME_FILES, GUI_RUNTIME_FILES
    files = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
             for relative in (GUI_RUNTIME_FILES if gui else PROJECT_RUNTIME_FILES if project else PUBLIC_RUNTIME_FILES)}
    return identity_from_files(files)


def temporary_usage(folder, limits=LIMITS):
    count = size = 0
    for directory, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            count += 1
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise WorkbenchError("TEMPORARY_LIMIT", "RESOURCE")
            if path.is_file():
                try:
                    size += path.stat().st_size
                except FileNotFoundError:
                    continue  # A completed host temporary publication may disappear.
            if count > limits["temporary_files"] or size > limits["temporary_bytes"]:
                raise WorkbenchError("TEMPORARY_LIMIT", "RESOURCE",
                    dict(temporary_peak_bytes=size, temporary_peak_entries=count))
    return count, size


def host_progress(folder, nonce, previous=None):
    path = folder / "host-progress.jsonl"
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
    value = (dict(ready_at=None, active_callbacks=[], callbacks=[], offset=0, last_sequence=0, last_timestamp=-1, done=False)
             if previous is None else previous)
    with path.open("rb") as stream:
        if path.stat().st_size < value["offset"]:
            raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
        stream.seek(value["offset"])
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
    complete = raw.rfind(b"\n") + 1
    if len(raw) - complete > 4096:
        raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
    for line in raw[:complete].splitlines(keepends=True):
        item = read_json(line)
        if (type(item) is not dict or set(item) != {"format", "version", "nonce", "event", "timestamp", "sequence", "member", "depth"}
                or item["format"] != "ultra-workbench-host-progress" or type(item["version"]) is not int
                or item["version"] != 1 or item["nonce"] != nonce or type(item["timestamp"]) not in {int, float}
                or not math.isfinite(item["timestamp"]) or item["timestamp"] < 0 or item["timestamp"] < value["last_timestamp"]
                or type(item["sequence"]) is not int or type(item["depth"]) is not int
                or not 0 <= item["depth"] < 16 or value["done"]):
            raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
        event = item["event"]
        value["last_timestamp"] = item["timestamp"]
        if event == "boot":
            if value["offset"] or item["sequence"] != 0 or item["member"] is not None:
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
        elif event == "ready":
            if value["ready_at"] is not None or item["member"] is not None:
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
            value["ready_at"] = item["timestamp"]
        elif event == "begin":
            if (item["member"] not in {"choose_action", "generate_terrain", "generate_level"}
                    or item["sequence"] != value["last_sequence"] + 1 or item["depth"] != len(value["active_callbacks"])
                    or value["ready_at"] is None):
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
            value["last_sequence"] = item["sequence"]
            value["active_callbacks"].append(dict(sequence=item["sequence"], member=item["member"],
                started=item["timestamp"], depth=item["depth"]))
        elif event == "end":
            if not value["active_callbacks"]:
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
            active = value["active_callbacks"].pop()
            if (any(item[key] != active[key] for key in ("sequence", "member", "depth"))
                    or item["timestamp"] < active["started"]):
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
            value["callbacks"].append(dict(sequence=item["sequence"], member=item["member"], depth=item["depth"],
                seconds=round(item["timestamp"] - active["started"], 9)))
        elif event == "done":
            if value["active_callbacks"] or value["ready_at"] is None or item["member"] is not None:
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
            value["done"] = True
        else:
            raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
        value["offset"] += len(line)
        if len(value["callbacks"]) > 4096:
            raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE")
    return value


def validated_diagnostic(value, workspace, manifest):
    """Accept only finite context and a location in the exact selected source."""
    if value is None:
        return None
    members = {
        "Character": {"__init__", "agent_id"},
        "Artifact": {"__init__", "artifact_id", "position", "value"},
        "Enemy": {"__init__", "enemy_id", "position", "encounter_penalty"},
        "AgentController": {"__init__", "choose_action"},
        "TerrainGenerator": {"__init__", "generate_terrain"},
        "LevelGenerator": {"__init__", "generate_level"},
    }
    kinds = {"NotImplementedError", "SyntaxError", "IndentationError", "ImportError",
             "AttributeError", "TypeError", "ValueError", "IndexError", "KeyError",
             "ZeroDivisionError", "RuntimeError", "OtherError", "ContractError"}
    if (type(value) is not dict or set(value) != {"component", "member", "file", "line", "exception_kind"}
            or type(value["component"]) is not str or value["component"] not in ENTRIES
            or (value["member"] is not None and (type(value["member"]) is not str
                or value["member"] not in members[value["component"]]))
            or type(value["exception_kind"]) is not str or value["exception_kind"] not in kinds
            or type(value["file"]) is not str or not value["file"].startswith("src/student/")
            or not value["file"].endswith(".py")):
        raise WorkbenchError("WORKER_PROTOCOL")
    try:
        raw = source_bytes(workspace, manifest, value["file"])
    except (OSError, SubmissionError):
        raise WorkbenchError("WORKER_PROTOCOL") from None
    if value["line"] is not None and (type(value["line"]) is not int
            or not 1 <= value["line"] <= len(raw.splitlines())):
        raise WorkbenchError("WORKER_PROTOCOL")
    return dict(value)


def execute(operation, workspace, payload=None, *, manifest=None, runtime=None, environment_variant="A", diagnostics=None,
            cancel_event=None, on_progress=None):
    """Only this package's fixed worker target executes captured selected code."""
    workspace = Path(workspace).resolve()
    last_phase = None
    def cancelled():
        return cancel_event is not None and cancel_event.is_set()
    def report(phase):
        nonlocal last_phase
        if phase != last_phase:
            last_phase = phase
            if on_progress is not None:
                on_progress(phase)
    if cancelled():
        raise WorkbenchError("CANCELLED", "CANCELLED")
    report("checking_sources")
    try:
        manifest = capture_sources(workspace) if manifest is None else manifest
        verify_sources(workspace, manifest)
    except (OSError, SubmissionError) as exc:
        raise WorkbenchError(getattr(exc, "code", "SOURCE_READ")) from None
    runtime = runtime_identity(project=operation.endswith("_v2")) if runtime is None else runtime
    project = operation.endswith("_v2")
    if project:
        from .resources import PROJECT_LIMITS, resource_policy
        limits = PROJECT_LIMITS
    else:
        limits = LIMITS
    limit = limits["controller_seconds" if operation in {"solve", "solve_v2"} else
                   "generation_seconds" if operation in {"generate", "generate_v2", "terrain_v2", "generation_probe_v2"}
                   else "import_seconds"]
    if cancelled():
        raise WorkbenchError("CANCELLED", "CANCELLED")
    nonce = uuid.uuid4().hex
    request = dict(operation=operation, workspace=str(workspace), manifest=manifest,
                   runtime_identity=runtime, payload=payload or {}, noise_seed=1001 if environment_variant == "A" else 2002,
                   project=project, progress_nonce=nonce)
    with tempfile.TemporaryDirectory(prefix="ultra-workbench-") as name:
        folder = Path(name).resolve()
        (folder / "request.json").write_bytes(encode(request))
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT),
               "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0" if environment_variant == "A" else "17"}
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == "nt" else {"start_new_session": True})
        if cancelled():
            raise WorkbenchError("CANCELLED", "CANCELLED")
        report("loading_components")
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-B", "-u", "-m", "src.workbench.worker", str(folder)],
            cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, **options)
        noise = [0, 0]
        captured = [bytearray(), bytearray()]
        noise_lock = threading.Lock()
        exceeded = threading.Event()
        def drain(pipe, index):
            try:
                while chunk := pipe.read1(4096):
                    with noise_lock:
                        noise[index] += len(chunk)
                        available = max(0, limits["output_bytes"] - sum(len(value) for value in captured))
                        captured[index].extend(chunk[:available])
                        if sum(noise) > limits["output_bytes"]:
                            exceeded.set()
            finally:
                pipe.close()
        threads = [threading.Thread(target=drain, args=(pipe, i), daemon=True)
                   for i, pipe in enumerate((process.stdout, process.stderr))]
        for thread in threads:
            thread.start()
        failure = None
        progress = None
        peak_files = peak_bytes = 0
        try:
            while process.poll() is None:
                if cancelled():
                    failure = "CANCELLED"; break
                if exceeded.is_set():
                    failure = "OUTPUT_LIMIT"; break
                try:
                    if project:
                        progress = host_progress(folder, nonce, progress)
                        if progress is not None and progress["active_callbacks"]:
                            report({"choose_action": "running_solution", "generate_terrain": "generating_terrain",
                                    "generate_level": "generating_level"}[progress["active_callbacks"][-1]["member"]])
                        now = time.monotonic()
                        if (progress is None or progress["ready_at"] is None) and now - started >= limits["import_seconds"]:
                            failure = "IMPORT_TIMEOUT"; break
                        if progress is not None and any(now - item["started"] >= limits["callback_seconds"]
                                                        for item in progress["active_callbacks"]):
                            failure = "CALLBACK_TIMEOUT"; break
                        if progress is not None and progress["ready_at"] is not None and now - progress["ready_at"] >= limit:
                            failure = "CONTROLLER_WHOLE_TIMEOUT" if operation == "solve_v2" else "GENERATION_TIMEOUT"; break
                        if now - started >= limits["worker_seconds"]:
                            failure = "WORKER_TIMEOUT"; break
                    elif time.monotonic() - started >= limit:
                        failure = "TIMEOUT"; break
                    count, size = temporary_usage(folder, limits)
                except WorkbenchError as exc:
                    failure = exc.code
                    if exc.resources is not None:
                        peak_files = max(peak_files, exc.resources.get("temporary_peak_entries", 0))
                        peak_bytes = max(peak_bytes, exc.resources.get("temporary_peak_bytes", 0))
                    break
                except (OSError, ValueError):
                    failure = "WORKER_PROGRESS_PROTOCOL" if project else "TEMPORARY_IO"
                    break
                peak_files, peak_bytes = max(peak_files, count), max(peak_bytes, size)
                time.sleep(0.01)
        finally:
            terminate(process)
            for thread in threads:
                thread.join(timeout=2)
        def worker_metrics(result_size=None):
            metrics = dict(pid=process.pid, exit_code=process.returncode,
                stdout_bytes=noise[0], stderr_bytes=noise[1], timeout_seconds=limit,
                elapsed_seconds=round(time.monotonic() - started,6), environment_variant=environment_variant,
                source_digest=source_identity(manifest)["sha256"], runtime_digest=runtime["sha256"], fresh_process=True)
            if project:
                callbacks = [] if progress is None else progress["callbacks"]
                metrics.update(resource_policy=resource_policy(),callbacks=callbacks,
                    import_seconds=None if progress is None or progress["ready_at"] is None else
                        round(max(0,progress["ready_at"]-started),6),
                    generation_seconds=round(sum(item["seconds"] for item in callbacks
                        if item["depth"] == 0 and item["member"] in {"generate_terrain","generate_level"}),6),
                    result_bytes=result_size,temporary_peak_bytes=peak_bytes,temporary_peak_entries=peak_files)
            return metrics
        if diagnostics is not None:
            target = Path(diagnostics).resolve()
            if target.exists() or any(target.is_relative_to(base) for base in (ROOT / "src", ROOT / "assets", workspace / "src")):
                raise WorkbenchError("DIAGNOSTIC_DESTINATION")
            target.mkdir(parents=True)
            (target / "stdout.bin").write_bytes(captured[0])
            (target / "stderr.bin").write_bytes(captured[1])
            marker = folder / "host-progress.jsonl"
            if marker.exists() and marker.stat().st_size <= 2 * 1024 * 1024:
                (target / "host-progress.jsonl").write_bytes(marker.read_bytes())
            (target / "worker.json").write_bytes(encode(dict(exit_code=process.returncode,
                stdout_bytes=noise[0], stderr_bytes=noise[1], bounded_capture_bytes=sum(map(len, captured)))))
        if cancelled() or failure == "CANCELLED":
            raise WorkbenchError("CANCELLED", "CANCELLED", worker_metrics())
        report("validating_result")
        try:
            verify_sources(workspace, manifest)
        except (OSError, SubmissionError):
            raise WorkbenchError("SOURCE_DRIFT",resources=worker_metrics() if project else None) from None
        if exceeded.is_set():
            failure = "OUTPUT_LIMIT"
        if failure:
            raise WorkbenchError(failure, "RESOURCE", worker_metrics())
        if process.returncode != 0 or not (folder / "result.json").is_file():
            raise WorkbenchError("WORKER_EXIT",resources=worker_metrics() if project else None)
        count, size = temporary_usage(folder, limits)
        peak_files, peak_bytes = max(peak_files, count), max(peak_bytes, size)
        if project:
            progress = host_progress(folder, nonce, progress)
            if progress is None or progress["ready_at"] is None or progress["active_callbacks"] or not progress["done"]:
                raise WorkbenchError("WORKER_PROGRESS_PROTOCOL", "RESOURCE",worker_metrics())
            if progress["ready_at"] - started >= limits["import_seconds"]:
                raise WorkbenchError("IMPORT_TIMEOUT", "RESOURCE",worker_metrics())
            if any(item["seconds"] >= limits["callback_seconds"] for item in progress["callbacks"]):
                raise WorkbenchError("CALLBACK_TIMEOUT", "RESOURCE",worker_metrics())
            if time.monotonic() - progress["ready_at"] >= limit:
                raise WorkbenchError("CONTROLLER_WHOLE_TIMEOUT" if operation == "solve_v2" else "GENERATION_TIMEOUT", "RESOURCE",worker_metrics())
        if (folder / "result.json").stat().st_size > limits["result_bytes"]:
            raise WorkbenchError("RESULT_LIMIT", "RESOURCE",worker_metrics() if project else None)
        with (folder / "result.json").open("rb") as stream:
            raw = stream.read(limits["result_bytes"] + 1)
        if len(raw) > limits["result_bytes"]:
            raise WorkbenchError("RESULT_LIMIT", "RESOURCE",worker_metrics() if project else None)
        result = read_json(raw)
        statuses = {"OK", "INCOMPLETE", "CONTRACT_FAILURE", "IMPORT_FAILURE", "CONFORMANCE_FAILURE"}
        if (type(result) is not dict or type(result.get("status")) is not str
                or result["status"] not in statuses):
            raise WorkbenchError("WORKER_PROTOCOL",resources=worker_metrics(len(raw)) if project else None)
        diagnostic = validated_diagnostic(result.get("diagnostic"), workspace, manifest)
        if result.get("status") != "OK":
            from src.framework.generation.level_execution import LEVEL_CODES
            from src.framework.terrain_generator_execution import _ERROR_CODES
            codes = set(LEVEL_CODES) | set(_ERROR_CODES) | {
                "TODO_IMPLEMENTATION", "FORBIDDEN_IMPORT", "SOURCE_DRIFT", "MISSING_COMPONENT",
                "CLASS_MISSING_OR_NOT_CLASS", "CONSTRUCTOR_SIGNATURE", "PUBLIC_MEMBER_SIGNATURE",
                "INPUT_NOT_PRESERVED", "PUBLIC_MEMBER_CONTRACT", "GENERATION_FAILURE", "COMPONENT_EXCEPTION",
                "TERRAIN_DEPENDENCY_NOT_USED", "CHARACTER_IDENTITY", "CONTRACT_SIGNATURE", "CHILD_PROCESS_FORBIDDEN",
                "INVALID_PUBLIC_CANDIDATE", "HOST_CONFIGURATION", "UNSUPPORTED_CHALLENGE",
                "PATROL_GENERATION_NOT_SUPPORTED", "ARTIFACT_IDENTITY", "ENEMY_IDENTITY"}
            codes.add("GENERATION_REPEATABILITY_FAILURE")
            code = result.get("code")
            if type(code) is not str or code not in codes:
                raise WorkbenchError("WORKER_PROTOCOL",resources=worker_metrics(len(raw)) if project else None)
            raise WorkbenchError(code,result["status"],worker_metrics(len(raw)) if project else None, diagnostic)
        if cancelled():
            raise WorkbenchError("CANCELLED", "CANCELLED", worker_metrics(len(raw)))
        result["worker"] = worker_metrics(len(raw))
        if diagnostic is not None:
            result["diagnostic"] = diagnostic
        return result
