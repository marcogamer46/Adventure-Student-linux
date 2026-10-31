"""All-tier public commands; compatible introductory commands remain separate."""
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import platform
import uuid
from src.framework.static_records import encode, read_json, ReplayError
from src.framework.public_practice.admission import CHALLENGE, PracticeError
from src.framework.public_practice.records import validate_identity

LEVEL_FORMAT = "ultra-public-project-level"
RUN_FORMAT = "ultra-public-project-run"
MANIFEST_FORMAT = "ultra-workbench-local-manifest"
AUTHORITY = "LOCAL_PUBLIC_PRACTICE_NO_GRADE"


def _configuration(args, bounded):
    from src.framework.public_project.catalog import configuration
    overrides = None if not args.config else read_json(bounded(args.config))
    return configuration(args.challenge, args.seed, overrides)


def _tracking(raw, data, generation_identity, resources_raw):
    return dict(format=MANIFEST_FORMAT, version=2, status="SAVED", run_id=uuid.uuid4().hex,
        recorded_utc=datetime.now(timezone.utc).isoformat(), run_sha256=hashlib.sha256(raw).hexdigest(),
        source_identity=data["source_identity"]["sha256"],
        runtime_identity=data["runtime_identity"]["sha256"], python=platform.python_version(),
        challenge=data["admission"]["configuration"]["scenario_id"],
        generation_source_identity=None if generation_identity is None else generation_identity["sha256"],
        resources_sha256=hashlib.sha256(resources_raw).hexdigest(),
        authority=AUTHORITY)


def save_run(folder, level_record, outcome, generation_identity, atomic, *, publish=True):
    from src.framework.public_project.recording import validate_record
    raw = encode(outcome["run"])
    view = validate_record(raw)
    data = read_json(raw)
    resources_raw = encode(dict(outcome['worker'],run_sha256=hashlib.sha256(raw).hexdigest()))
    tracking = _tracking(raw, data, generation_identity, resources_raw)
    atomic(folder / "level.json", encode(level_record))
    atomic(folder / "run.json", raw)
    atomic(folder / "resources.json", resources_raw)
    if publish:
        atomic(folder / "manifest.json", encode(tracking))
        atomic(folder / "attempt.json", encode(dict(status="SAVED", outcome=outcome["outcome"], code=outcome["code"])))
    return view, tracking


def _generation_identity(path, level_record, bounded):
    companion = Path(str(path) + ".manifest.json")
    if not companion.exists():
        return None
    provenance = read_json(bounded(companion))
    if (type(provenance) is not dict or set(provenance) != {"format", "version", "level_sha256",
            "source_identity", "runtime_identity", "authority"}
            or provenance["format"] != "ultra-workbench-generation-provenance"
            or type(provenance["version"]) is not int or provenance["version"] != 2
            or provenance["level_sha256"] != hashlib.sha256(encode(level_record)).hexdigest()
            or provenance["authority"] != "LOCAL_PUBLIC_CONTENT_BINDING_ONLY"):
        raise PracticeError("GENERATION_PROVENANCE_MISMATCH")
    validate_identity(provenance["runtime_identity"])
    return validate_identity(provenance["source_identity"])


def show(raw, *, headless=False):
    from src.framework.public_project.recording import validate_record
    view = validate_record(raw)
    data = read_json(raw)
    if headless:
        return dict(status="OK", scope="public-development", student_code_executed=False,
            source_identity=data["source_identity"]["sha256"], frames=len(view.snapshots),
            result=view.summary, authority="LOCAL_CONSISTENCY_ONLY_NO_GRADE")
    if importlib.util.find_spec("PIL") is None:
        raise PracticeError("VIEWER_PILLOW_REQUIRED")
    from src.renderer.expedition.practice import load_public
    from src.renderer.expedition.view import ExpeditionViewer, ViewerUnavailableError
    root = Path(__file__).resolve().parents[2]
    try:
        ExpeditionViewer({"practice": load_public(raw, title="Saved Adventure practice")}, selected="practice",
            asset_manifest=root / "assets/presentation/asset-manifest-v2.json", public_showcase=False).run()
    except ViewerUnavailableError:
        raise PracticeError("VIEWER_UNAVAILABLE") from None
    return dict(status="OK", scope="public-development", student_code_executed=False, authority=AUTHORITY)


def _replay(args, bounded):
    folder = Path(args.run)
    raw = bounded(folder / "run.json")
    data = read_json(raw)
    if type(data) is not dict or data.get("format") != RUN_FORMAT:
        return None
    from src.framework.public_project.recording import validate_record
    validate_record(raw)
    tracking = read_json(bounded(folder / "manifest.json"))
    keys = {"format", "version", "status", "run_id", "recorded_utc", "run_sha256", "source_identity",
            "runtime_identity", "python", "challenge", "generation_source_identity", "resources_sha256", "authority"}
    resources_raw = bounded(folder / "resources.json")
    resources = read_json(resources_raw)
    generation = data.get("generation_identity")
    expected_generation = None if generation is None else validate_identity(generation)["sha256"]
    if (type(tracking) is not dict or set(tracking) != keys or tracking["format"] != MANIFEST_FORMAT
            or type(tracking["version"]) is not int or tracking["version"] != 2
            or tracking["status"] != "SAVED" or tracking["authority"] != AUTHORITY
            or tracking["run_sha256"] != hashlib.sha256(raw).hexdigest()
            or type(resources) is not dict or resources.get("fresh_process") is not True
            or resources.get('source_digest') != data['source_identity']['sha256']
            or resources.get('runtime_digest') != data['runtime_identity']['sha256']
            or resources.get('run_sha256') != hashlib.sha256(raw).hexdigest()
            or tracking["resources_sha256"] != hashlib.sha256(resources_raw).hexdigest()
            or tracking["source_identity"] != data["source_identity"]["sha256"]
            or tracking["runtime_identity"] != data["runtime_identity"]["sha256"]
            or tracking["generation_source_identity"] != expected_generation
            or tracking["challenge"] != data["admission"]["configuration"]["scenario_id"]):
        raise PracticeError("RUN_MANIFEST_MISMATCH")
    return show(raw, headless=args.headless), 0


def dispatch(args, workspace, *, bounded, destination, reserve, atomic):
    """Return None for an existing v1 operation, otherwise a public result/code."""
    command = args.command
    if command in {"challenges", "describe"}:
        from src.framework.public_project.catalog import list_challenges
        from .resources import resource_policy
        descriptions = list_challenges()
        if command == "describe":
            items = descriptions["challenges"] if type(descriptions) is dict else descriptions
            selected = [item for item in items if item.get("scenario_id", item.get("challenge")) == args.challenge]
            if len(selected) != 1:
                raise PracticeError("UNSUPPORTED_CHALLENGE")
            descriptions = selected[0]
        return dict(status="OK", scope="public-development", catalog=descriptions,
                    resources=resource_policy(), all_tiers_available=True,
                    student_code_executed=False, official_grade="NOT_COMPUTED"), 0
    if command == "replay":
        return _replay(args, bounded)
    if command in {"validate", "solve"}:
        data = read_json(bounded(args.level))
        if type(data) is not dict or data.get("format") != LEVEL_FORMAT:
            return None
        from src.framework.public_project.recording import read_level
        level, config, admission = read_level(data)
        if command == "validate":
            return dict(status="OK", challenge=config["scenario_id"], tier=config["tier"],
                baseline_cost=admission["baseline_cost"], student_code_executed=False,
                authority="PUBLIC_DEVELOPMENT_INDEPENDENT_ADMISSION"), 0
        generation = _generation_identity(args.level, data, bounded)
        folder = destination(args.output, workspace, directory=True)
        reserve(folder, directory=True)
        try:
            from .process import execute, runtime_identity, source_identity
            from src.framework.submission.identity import capture_sources, verify_sources
            manifest = capture_sources(workspace)
            runtime = runtime_identity(project=True)
            outcome = execute("solve_v2", workspace, dict(level=data, generation_identity=generation),
                              manifest=manifest, runtime=runtime)
            verify_sources(workspace, manifest)
            view, tracking = save_run(folder, data, outcome, generation, atomic)
            return dict(status="COMPLETED" if view.summary["completed"] else "FAILED_RUN_SAVED",
                outcome=outcome["outcome"], code=outcome["code"], run=str(folder),
                source_identity=source_identity(manifest)["sha256"],
                generation_source_identity=tracking["generation_source_identity"], metrics=view.summary,
                whole_project_readiness="NOT_ASSESSED", official_grade="NOT_COMPUTED", worker=outcome["worker"]),\
                0 if view.summary["completed"] else 1
        except BaseException as exc:
            atomic(folder / "attempt.json", encode(dict(status=getattr(exc, "status", "REJECTED"),
                code=getattr(exc, "code", "INPUT_OR_HOST_ERROR"))))
            raise
    if command == "diagnose":
        folder = destination(args.output, workspace, directory=True)
        reserve(folder, directory=True)
        from .suite import run_suite
        report = run_suite(workspace, folder, tier=args.tier, atomic=atomic)
        public_result = report if args.details else dict(status="SAVED", outcome=report["outcome"],
            assessed_scope=report["assessed_scope"], actual_case_executions=report["actual_case_executions"],
            inherited_case_references=report["inherited_case_references"], source_valid=report["source_valid"],
            source_identity=report["source_identity"]["sha256"], report=str(folder / "report.json"),
            official_grade="NOT_COMPUTED", instructor_assessment="SEPARATE_REQUIRED")
        return public_result, 0 if report["outcome"] == "PASS" else 1
    if command not in {"example", "generate"} or (command == "generate" and args.challenge == CHALLENGE):
        return None
    from src.framework.public_project.catalog import example_level
    from src.framework.public_project.preparation import prepare_level
    config = _configuration(args, bounded)
    path = destination(args.output, workspace)
    if command == "generate" and config["tier"] == 8:
        raise PracticeError("PATROL_GENERATION_NOT_SUPPORTED")
    provenance = None
    if command == "generate":
        provenance = destination(str(path) + ".manifest.json", workspace)
    reserve(path)
    try:
        if command == "example":
            record = prepare_level(example_level(config), config)
            atomic(path, encode(record))
            return dict(status="OK", level=str(path), challenge=config["scenario_id"], tier=config["tier"],
                student_code_executed=False, purpose="INDEPENDENT_PUBLIC_CONTROLLER_INPUT"), 0
        from .process import execute, runtime_identity, source_identity
        from src.framework.submission.identity import capture_sources, verify_sources
        from src.framework.generation.canonical import read_level as read_candidate
        manifest = capture_sources(workspace)
        runtime = runtime_identity(project=True)
        outcome = execute("terrain_v2" if args.kind == "terrain" else "generate_v2", workspace,
            dict(configuration=config, dependency=args.dependency), manifest=manifest, runtime=runtime)
        if args.kind == "terrain":
            record = dict(format="ultra-public-project-terrain", version=2, configuration=config,
                          terrain=outcome["terrain"])
        else:
            record = prepare_level(read_candidate(outcome["level"]), config)
        verify_sources(workspace, manifest)
        raw = encode(record)
        atomic(path, raw)
        with provenance.open("xb") as stream:
            stream.write(encode(dict(format="ultra-workbench-generation-provenance", version=2,
                level_sha256=hashlib.sha256(raw).hexdigest(), source_identity=source_identity(manifest),
                runtime_identity=runtime, authority="LOCAL_PUBLIC_CONTENT_BINDING_ONLY")))
        return dict(status="OK", level=str(path), challenge=config["scenario_id"], tier=config["tier"],
            kind=args.kind, dependency=None if args.kind == "terrain" else args.dependency,
            generation_source_identity=source_identity(manifest)["sha256"], provenance=str(provenance),
            terrain_calls=outcome.get("terrain_calls"), worker=outcome["worker"]), 0
    except BaseException as exc:
        atomic(path, encode(dict(status=getattr(exc, "status", "REJECTED"),
                                code=getattr(exc, "code", "INPUT_OR_HOST_ERROR"))))
        raise
