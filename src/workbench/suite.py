"""Finite public diagnosis across independent lanes on one immutable source."""
import hashlib
from pathlib import Path
import time
from src.framework.static_records import encode
from src.framework.public_practice.records import identity_from_files
from src.framework.submission.identity import capture_sources, verify_sources
from .process import execute, runtime_identity, source_identity, WorkbenchError
from .project import save_run


def prerequisites(case, level=None):
    lane = case["lane"]
    if lane == "T":
        return ["TerrainGenerator"]
    if lane == "G":
        return ["LevelGenerator"] + ([] if case["dependency"] == "reference" else ["TerrainGenerator"])
    if lane == "I":
        names = ["TerrainGenerator", "LevelGenerator", "Character", "AgentController"]
    else:
        names = ["Character", "AgentController"]
    if level is not None or "configuration" in case:
        spec = case.get("configuration", {}).get("specification", {})
        if level.artifacts if level is not None else spec.get("artifact_count", 0):
            names.append("Artifact")
        if level.enemies if level is not None else spec.get("enemy_count", 0):
            names.append("Enemy")
    return names


def case_digest(case):
    return hashlib.sha256(encode(case)).hexdigest()


def validate_case_set(cases):
    """Bind every required public instance before any selected source executes."""
    from src.framework.public_project.catalog import list_challenges, configuration, example_level
    from src.framework.generation.canonical import level_record
    expected = []
    for description in list_challenges():
        tier, scenario = description["tier"], description["scenario_id"]
        for seed in description["public_seeds"]:
            config = configuration(scenario, seed, {"reverse":seed == 29 and tier != 8})
            for lane, dependency in (("C",None),) if tier == 8 else (
                    ("T",None),("G","reference"),("G","student"),("C",None),("I",None)):
                item = dict(case_id=f"{scenario}-{seed}-{lane}" + ("-"+dependency if dependency else ""),
                    scenario_id=scenario,tier=tier,lane=lane,dependency=dependency,configuration=config)
                if lane == "C":
                    item["level"] = level_record(example_level(config))
                expected.append(item)
    ids = [case.get("case_id") for case in cases if type(case) is dict]
    if (len(ids) != len(cases) or len(ids) != len(set(ids))
            or encode(sorted(cases,key=lambda item:item["case_id"])) != encode(sorted(expected,key=lambda item:item["case_id"]))):
        raise WorkbenchError("PUBLIC_CASE_SET_INVALID")
    return tuple(expected)


def _stored(folder, name):
    path = folder / name
    if path.is_symlink() or getattr(path, "is_junction", lambda:False)() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("EVIDENCE_FILE_BOUNDARY")
    from src.framework.static_records import read_json
    raw = path.read_bytes()
    value = read_json(raw)
    if raw != encode(value):
        raise ValueError("EVIDENCE_SERIALIZATION")
    return value


def _dependency_trace(trace, spec, seed, candidate):
    from src.framework.generation import canonical
    from src.framework.terrain_validation import validate_terrain_candidate
    if type(trace) is not list or not 1 <= len(trace) <= spec.max_attempts:
        raise ValueError("DEPENDENCY_TRACE")
    last_seed = seed - 1
    terrains = []
    fields = {"call","request","invoked","status","category","code","stage","detail_code","candidate","digest"}
    for index, call in enumerate(trace,1):
        if (type(call) is not dict or set(call) != fields or call["call"] != index
                or call["invoked"] is not True or call["status"] != "PASS" or call["category"] != "SUCCESS"
                or call["code"] != "OK" or call["stage"] != "terrain-validation" or call["detail_code"] is not None):
            raise ValueError("DEPENDENCY_TRACE")
        terrain_spec, given_seed = canonical.read_terrain_request(call["request"])
        if (canonical.terrain_request(terrain_spec,0) != canonical.terrain_request(spec.terrain_spec,0)
                or (index == 1 and given_seed != seed) or not last_seed < given_seed < seed + spec.max_attempts):
            raise ValueError("DEPENDENCY_REQUEST")
        last_seed = given_seed
        terrain = canonical.read_terrain(call["candidate"])
        validate_terrain_candidate(terrain, terrain_spec)
        if call["digest"] != canonical.digest(call["candidate"]):
            raise ValueError("DEPENDENCY_DIGEST")
        terrains.append(call["candidate"])
    if not any(encode(terrain) == encode(candidate["terrain"]) for terrain in terrains):
        raise ValueError("DEPENDENCY_CONTENT_BINDING")


def _generation_evidence(detail, case, source_digest, runtime_digest):
    from src.framework.public_project.catalog import configuration, request
    from src.framework.generation import canonical
    from src.framework.terrain_validation import validate_terrain_candidate
    from src.framework.level_patrol_validation import validate_level_patrol_candidate
    config = case["configuration"]
    alternate = configuration(config["scenario_id"], config["seed"] + 101, config["overrides"])
    inputs = {"A":request(config),"B":request(alternate)}
    terrain_kind = case["lane"] == "T"
    if (type(detail) is not dict or set(detail) != {"outcome","code","sessions","workers"}
            or detail["outcome"] != "PASS" or detail["code"] != "DETERMINISTIC_VALID_PUBLIC_CANDIDATE"
            or len(detail["sessions"]) != 2 or len(detail["workers"]) != 2):
        raise ValueError("GENERATION_EVIDENCE")
    primaries = []
    layout = (("A1","A",0),("A2","A",0),("B","B",0),("A3","A",0),("A4","A",1))
    pids = []
    for session, worker, variant in zip(detail["sessions"],detail["workers"],("A","B")):
        if (type(session) is not dict or set(session) != {"kind","status","category","code","stage","detail_code",
                "fresh_instance","comparison","trials"} or session["kind"] != ("terrain-session" if terrain_kind else "level-session")
                or session["status"] != "PASS" or session["category"] != "SUCCESS" or session["code"] != "OK"
                or session["stage"] != "comparison" or session["detail_code"] is not None
                or session["fresh_instance"] is not True or session["comparison"] != "MATCH" or len(session["trials"]) != 5
                or worker["source_digest"] != source_digest or worker["runtime_digest"] != runtime_digest
                or worker["fresh_process"] is not True or worker["environment_variant"] != variant
                or type(worker["pid"]) is not int or worker["pid"] <= 0 or worker["exit_code"] != 0):
            raise ValueError("GENERATION_EVIDENCE")
        pids.append(worker["pid"])
        for trial, (label,which,instance) in zip(session["trials"],layout):
            fields = {"trial","request","instance","invoked","status","category","code","stage","detail_code","candidate","digest"}
            if not terrain_kind:
                fields.add("dependency_trace")
            if (type(trial) is not dict or set(trial) != fields or trial["trial"] != label or trial["request"] != which
                    or type(trial["instance"]) is not int or trial["instance"] != instance or trial["invoked"] is not True
                    or trial["status"] != "PASS" or trial["category"] != "SUCCESS" or trial["code"] != "OK"
                    or trial["stage"] != ("terrain-validation" if terrain_kind else "level-validation") or trial["detail_code"] is not None):
                raise ValueError("GENERATION_TRIAL")
            spec, seed = inputs[which]
            candidate = trial["candidate"]
            if trial["digest"] != canonical.digest(candidate):
                raise ValueError("GENERATION_DIGEST")
            if terrain_kind:
                validate_terrain_candidate(canonical.read_terrain(candidate),spec.terrain_spec)
            else:
                validate_level_patrol_candidate(canonical.read_level(candidate),spec,seed,provenance="student-static")
                _dependency_trace(trial["dependency_trace"],spec,seed,candidate)
            if which == "A":
                primaries.append(candidate)
    if len(set(pids)) != 2 or any(encode(candidate) != encode(primaries[0]) for candidate in primaries):
        raise ValueError("GENERATION_REPEATABILITY")
    return primaries[0]


def _verify_positive(folder, observation, case, source_digest, runtime_digest):
    """Verify stored positive evidence with validators only, never student execution."""
    from src.framework.static_records import read_json
    from src.framework.public_project.recording import read_level, validate_record
    if case["lane"] in {"C", "I"}:
        data = _stored(folder,"run.json")
        raw = encode(data)
        view = validate_record(raw)
        if (not view.summary["completed"] or encode(view.summary) != encode(observation["gameplay"])
                or observation["code"] != view.summary["code"]
                or encode(data["admission"]["configuration"]) != encode(case["configuration"])
                or data["source_identity"]["sha256"] != source_digest
                or data["runtime_identity"]["sha256"] != runtime_digest
                or ((None if data["generation_identity"] is None else data["generation_identity"]["sha256"])
                    != (source_digest if case["lane"] == "I" else None))):
            raise ValueError("CASE_RECORD_BINDING")
        if case["lane"] == "C" and encode(data["admission"]["level"]) != encode(case["level"]):
            raise ValueError("INDEPENDENT_CONTROLLER_INPUT_BINDING")
        from types import SimpleNamespace
        from .project import _replay
        def bounded(path):
            candidate = Path(path)
            if candidate.parent != folder or candidate.is_symlink() or candidate.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("CASE_RECORD_BOUNDARY")
            return candidate.read_bytes()
        _replay(SimpleNamespace(run=folder,headless=True),bounded)
        if (encode(_stored(folder,"resources.json")) != encode(dict(observation['worker'],run_sha256=hashlib.sha256(raw).hexdigest()))
                or encode(_stored(folder,"level.json")) != encode(data["admission"])):
            raise ValueError("CASE_SIDECAR_BINDING")
        if case["lane"] == "I":
            generated = _stored(folder,"generation.json")
            from src.framework.public_project.catalog import request
            from src.framework.generation import canonical
            if (set(generated) != {"source_identity","runtime_identity","candidate","terrain_calls","dependency_trace","worker"}
                    or generated["source_identity"]["sha256"] != source_digest
                    or generated["runtime_identity"]["sha256"] != runtime_digest
                    or encode(generated["candidate"]) != encode(data["admission"]["level"])
                    or generated["terrain_calls"] != len(generated["dependency_trace"])
                    or generated["worker"]["source_digest"] != source_digest
                    or generated["worker"]["runtime_digest"] != runtime_digest
                    or generated["worker"]["fresh_process"] is not True
                    or generated["worker"]["pid"] == observation["worker"]["pid"]):
                raise ValueError("INTEGRATED_GENERATION_BINDING")
            _dependency_trace(generated["dependency_trace"],*request(case["configuration"]),generated["candidate"])
    else:
        detail = _stored(folder,"generation.json")
        primary = _generation_evidence(detail,case,source_digest,runtime_digest)
        if case["lane"] == "G":
            level, config, admission = read_level(_stored(folder,"level.json"))
            if encode(config) != encode(case["configuration"]) or encode(admission["level"]) != encode(primary):
                raise ValueError("GENERATION_ADMISSION_BINDING")


def inherited_static(cases, *, source_digest, batch_id, required_cases=None, runtime_digest=None, evidence_root=None):
    """Each Tier-8 retained category references every actual static case in its lane."""
    retained = []
    if required_cases is None:
        from src.framework.public_project.catalog import public_cases
        required_cases = validate_case_set(public_cases())
    else:
        required_cases = validate_case_set(required_cases)
    for lane in ("T", "G", "I"):
        expected = [case for case in required_cases if case["tier"] < 8 and case["lane"] == lane]
        required = [case for case in cases if case["tier"] < 8 and case["lane"] == lane]
        expected_map = {case["case_id"]:case for case in expected}
        ids = [case["case_id"] for case in required]
        valid = (set(ids) == set(expected_map) and len(ids) == len(set(ids)) and bool(expected)
                 and {case["tier"] for case in expected} == set(range(8)))
        if valid:
            try:
                for row in required:
                    definition = expected_map[row["case_id"]]
                    if (row["source_identity"] != source_digest or row["runtime_identity"] != runtime_digest
                            or row["batch_id"] != batch_id or row["case_definition_sha256"] != case_digest(definition)
                            or row["configuration_sha256"] != case_digest(definition["configuration"])
                            or row["category"] != "PT" + str(definition["tier"]) + "-" + definition["lane"]
                            or any(row[key] != definition[key] for key in ("tier","lane","scenario_id","dependency"))
                            or row["prerequisites"] != prerequisites(definition) or evidence_root is None):
                        raise ValueError("CASE_BINDING")
                    reference = row["evidence"]
                    relative = Path(reference["path"])
                    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != reference["path"]:
                        raise ValueError("EVIDENCE_PATH")
                    path = (Path(evidence_root) / relative).resolve()
                    if not path.is_relative_to(Path(evidence_root).resolve()):
                        raise ValueError("EVIDENCE_PATH")
                    if path.name != "result.json" or path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
                        raise ValueError("EVIDENCE_PATH")
                    raw = path.read_bytes()
                    observed = {key:value for key,value in row.items() if key != "evidence"}
                    if hashlib.sha256(raw).hexdigest() != reference["sha256"] or raw != encode(observed):
                        raise ValueError("EVIDENCE_SHA")
                    if row["outcome"] == "PASS":
                        if row["execution"] != "EXECUTED":
                            raise ValueError("NO_EXECUTION")
                        _verify_positive(path.parent, observed, definition, source_digest, runtime_digest)
            except Exception:
                valid = False
        if not valid:
            outcome, code = "INCOMPLETE", "INHERITED_STATIC_COVERAGE_MISSING"
        elif any(case["outcome"] == "INCOMPLETE" for case in required):
            outcome, code = "INCOMPLETE", "INHERITED_STATIC_UNRESOLVED"
        elif any(case["outcome"] != "PASS" for case in required):
            outcome, code = "FAIL", "INHERITED_STATIC_FAILURE"
        else:
            outcome, code = "PASS", "COMPLETE_SAME_BATCH_STATIC_COVERAGE"
        retained.append(dict(category="PT8-" + lane, lane=lane, outcome=outcome, code=code,
            source_identity=source_digest, batch_id=batch_id, actual_executions=0,
            runtime_identity=runtime_digest,
            inherited_case_ids=[case["case_id"] for case in required],
            inherited_evidence=[case.get("evidence") for case in required],
            required_case_count=len(expected), inherited_case_count=len(required)))
    return retained


def _generation(case, workspace, manifest, runtime):
    from src.framework.public_project.catalog import configuration
    from src.framework.public_project.preparation import prepare_level
    from src.framework.generation.canonical import read_level
    config = case["configuration"]
    alternate = configuration(config["scenario_id"], config["seed"] + 101, config["overrides"])
    kind = "terrain" if case["lane"] == "T" else "level"
    payload = dict(configuration=config, alternate=alternate, kind=kind, dependency=case["dependency"])
    outcomes = [execute("generation_probe_v2", workspace, payload, manifest=manifest, runtime=runtime,
                        environment_variant=variant) for variant in ("A", "B")]
    sessions = [outcome["session"] for outcome in outcomes]
    if any(session["status"] != "PASS" for session in sessions):
        return dict(outcome="FAIL", code="GENERATION_REPEATABILITY_FAILURE", sessions=sessions,
                    workers=[item["worker"] for item in outcomes]), None
    if kind == "level" and any(not trial["dependency_trace"] or
            any(call["status"] != "PASS" for call in trial["dependency_trace"])
            for session in sessions for trial in session["trials"]):
        return dict(outcome="FAIL", code="TERRAIN_DEPENDENCY_NOT_USED", sessions=sessions,
                    workers=[item["worker"] for item in outcomes]), None
    primaries = [trial["candidate"] for session in sessions for trial in session["trials"]
                 if trial["request"] == "A"]
    if not primaries or any(encode(candidate) != encode(primaries[0]) for candidate in primaries):
        return dict(outcome="FAIL", code="FRESH_PROCESS_CONTENT_MISMATCH", sessions=sessions,
                    workers=[item["worker"] for item in outcomes]), None
    admitted = None if kind == "terrain" else prepare_level(read_level(primaries[0]), config)
    return dict(outcome="PASS", code="DETERMINISTIC_VALID_PUBLIC_CANDIDATE", sessions=sessions,
                workers=[item["worker"] for item in outcomes]), admitted


def run_suite(workspace, folder, *, tier=None, atomic):
    from src.framework.public_project.catalog import public_cases, example_level
    from src.framework.public_project.preparation import prepare_level
    from src.framework.public_project.recording import read_level
    from src.framework.generation.canonical import read_level as read_candidate
    import uuid
    workspace, folder = Path(workspace), Path(folder)
    cases = tuple(public_cases())
    expected = validate_case_set(cases)
    if tier is not None:
        cases = tuple(case for case in cases if case["tier"] == tier)
    manifest = capture_sources(workspace)
    identity, runtime = source_identity(manifest), runtime_identity(project=True)
    batch = uuid.uuid4().hex
    rows, source_valid = [], True
    for index, case in enumerate(cases):
        started = time.monotonic()
        row = dict(case_id=case["case_id"], category="PT" + str(case["tier"]) + "-" + case["lane"],
            tier=case["tier"], lane=case["lane"], scenario_id=case["scenario_id"],
            dependency=case["dependency"], source_identity=identity["sha256"], batch_id=batch,
            runtime_identity=runtime["sha256"], case_definition_sha256=case_digest(case),
            configuration_sha256=case_digest(case["configuration"]),
            execution="NOT_EXECUTED_ADMISSION", prerequisites=prerequisites(case))
        target = folder / (str(index).zfill(3) + "-" + case["case_id"])
        target.mkdir()
        atomic(target / "attempt.json", encode(dict(status="INCOMPLETE", code="ATTEMPT_STARTED")))
        try:
            if not source_valid:
                row.update(outcome="INCOMPLETE", code="SOURCE_DRIFT", execution="NOT_EXECUTED_SOURCE_INVALID")
            elif case["lane"] in {"T", "G"}:
                row["execution"] = "ATTEMPTED"
                detail, admitted = _generation(case, workspace, manifest, runtime)
                row["execution"] = "EXECUTED"
                row.update({key: detail[key] for key in ("outcome", "code")})
                atomic(target / "generation.json", encode(detail))
                if admitted is not None:
                    atomic(target / "level.json", encode(admitted))
            else:
                generation_identity = None
                if case["lane"] == "I":
                    row["execution"] = "ATTEMPTED"
                    generated = execute("generate_v2", workspace,
                        dict(configuration=case["configuration"], dependency="student"),
                        manifest=manifest, runtime=runtime)
                    row["execution"] = "EXECUTED"
                    prepared = prepare_level(read_candidate(generated["level"]), case["configuration"])
                    generation_identity = identity
                    atomic(target / "generation.json", encode(dict(
                        source_identity=identity, runtime_identity=runtime,
                        candidate=generated["level"], terrain_calls=generated["terrain_calls"],
                        dependency_trace=generated["dependency_trace"], worker=generated["worker"])))
                else:
                    prepared = prepare_level(example_level(case["configuration"]), case["configuration"])
                level, config, admission = read_level(prepared)
                row["prerequisites"] = prerequisites(case, level)
                row["execution"] = "ATTEMPTED" if row["execution"] != "EXECUTED" else "EXECUTED"
                outcome = execute("solve_v2", workspace,
                    dict(level=prepared, generation_identity=generation_identity), manifest=manifest, runtime=runtime)
                row["execution"] = "EXECUTED"
                view, tracking = save_run(target, prepared, outcome, generation_identity, atomic)
                row.update(outcome="PASS" if view.summary["completed"] else "FAIL", code=view.summary["code"],
                           gameplay=view.summary, worker=outcome["worker"])
            verify_sources(workspace, manifest)
        except Exception as exc:
            code = getattr(exc, "code", "PUBLIC_HOST_OR_INPUT_ERROR")
            status = getattr(exc, "status", "INCOMPLETE")
            row.update(outcome="FAIL" if status in {"CONFORMANCE_FAILURE", "CONTRACT_FAILURE", "IMPORT_FAILURE"}
                       else "INCOMPLETE", code=code)
            if getattr(exc, "resources", None) is not None:
                row["resources"] = exc.resources
                if type(exc.resources.get("pid")) is int:
                    row["execution"] = "EXECUTED"
            if code == "SOURCE_DRIFT":
                source_valid = False
        row["elapsed_seconds"] = round(time.monotonic() - started, 6)
        observed = encode(row)
        atomic(target / "result.json", observed)
        row["evidence"] = dict(path=(target / "result.json").relative_to(folder).as_posix(),
                               sha256=hashlib.sha256(observed).hexdigest())
        atomic(target / "attempt.json", encode(dict(status="SAVED", outcome=row["outcome"], code=row["code"])))
        rows.append(row)
    try:
        verify_sources(workspace, manifest)
    except Exception:
        source_valid = False
    inherited = (inherited_static(rows, source_digest=identity["sha256"], batch_id=batch,
        required_cases=expected, runtime_digest=runtime["sha256"], evidence_root=folder) if tier is None else [])
    outcomes = [row["outcome"] for row in rows + inherited]
    outcome = ("INCOMPLETE" if not source_valid or "INCOMPLETE" in outcomes else
               "FAIL" if "FAIL" in outcomes or not outcomes else "PASS")
    report = dict(format="ultra-public-project-diagnostic", version=2, scope="public-development",
        assessed_scope="FULL_0_8_PUBLIC_DIAGNOSTIC" if tier is None else "SUBSET_TIER_" + str(tier),
        development_only=True, batch_id=batch, source_identity=identity, runtime_identity=runtime,
        source_valid=source_valid, outcome=outcome, actual_case_executions=sum(
            row["execution"] == "EXECUTED" for row in rows), cases=rows, inherited=inherited,
        inherited_case_references=sum(row["inherited_case_count"] for row in inherited),
        required_case_set_sha256=case_digest(list(expected)),
        required_categories=(["PT8-C"] if tier == 8 else ["PT" + str(t) + "-" + lane
            for t in (range(9) if tier is None else [tier]) for lane in "TGCI"]),
        retained_categories_not_assessed=["PT8-T","PT8-G","PT8-I"] if tier == 8 else [], official_grade="NOT_COMPUTED",
        instructor_assessment="SEPARATE_REQUIRED", authority="LOCAL_PUBLIC_DIAGNOSTIC_NO_GRADE")
    atomic(folder / "report.json", encode(report))
    atomic(folder / "attempt.json", encode(dict(status="SAVED", outcome=outcome, source_valid=source_valid)))
    return report
