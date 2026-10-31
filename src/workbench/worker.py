"""Fixed private worker entry for public development callbacks; never a grader."""
import inspect
import os
from pathlib import Path
import sys
import time
from src.api import (Position, to_character_definition, to_artifact_definition,
                     to_enemy_definition, GenerationFailure, ContractViolation)
from src.framework.submission.identity import (ENTRIES, SubmissionError, source_bytes, verify_sources)
from src.framework.submission.loader import StudentLoader, ImportBoundaryError
from src.framework.static_records import encode, read_json
from src.framework.generation.level_execution import LevelExecutionError
from src.framework.terrain_generator_execution import TerrainGeneratorExecutionError
from src.framework.public_practice.admission import PracticeError

PROGRESS = None
SOURCE_ROOT = None
SOURCE_MANIFEST = None


def student_diagnostic(exc, component=None, member=None):
    """Select a verified student frame, never an exception message or traceback."""
    if SOURCE_ROOT is None or SOURCE_MANIFEST is None:
        return None
    selected = {str(SOURCE_ROOT / item["path"]): item["path"]
                for item in SOURCE_MANIFEST["sources"]
                if item["path"].startswith("src/student/") and item["path"].endswith(".py")}
    relative = line = frame_member = None
    current = exc.__traceback__
    while current is not None:
        filename = current.tb_frame.f_code.co_filename
        if filename in selected:
            relative, line = selected[filename], current.tb_lineno
            frame_member = current.tb_frame.f_code.co_name
        current = current.tb_next
    if type(exc) in (SyntaxError, IndentationError, TabError) and exc.filename in selected:
        relative, line = selected[exc.filename], exc.lineno
    if component not in ENTRIES:
        component = next((name for name, filename in ENTRIES.items() if filename == relative), None)
    if component is None:
        return None
    if relative is None:
        relative = ENTRIES[component]
    members = {
        "Character": {"__init__", "agent_id"},
        "Artifact": {"__init__", "artifact_id", "position", "value"},
        "Enemy": {"__init__", "enemy_id", "position", "encounter_penalty"},
        "AgentController": {"__init__", "choose_action"},
        "TerrainGenerator": {"__init__", "generate_terrain"},
        "LevelGenerator": {"__init__", "generate_level"},
    }
    if member is None and relative == ENTRIES[component] and frame_member in members[component]:
        member = frame_member
    if member not in members[component]:
        member = None
    try:
        raw = source_bytes(SOURCE_ROOT, SOURCE_MANIFEST, relative)
    except (OSError, SubmissionError):
        return None
    if type(line) is not int or not 1 <= line <= len(raw.splitlines()):
        line = None
    kinds = {NotImplementedError: "NotImplementedError", SyntaxError: "SyntaxError",
             IndentationError: "IndentationError", TabError: "IndentationError",
             ImportError: "ImportError", ModuleNotFoundError: "ImportError",
             AttributeError: "AttributeError", TypeError: "TypeError", ValueError: "ValueError",
             IndexError: "IndexError", KeyError: "KeyError", ZeroDivisionError: "ZeroDivisionError",
             RuntimeError: "RuntimeError"}
    return dict(component=component, member=member, file=relative, line=line,
                exception_kind=kinds.get(type(exc), "OtherError"))


class HostProgress:
    """Nonce-bound host timing; public callbacks cannot supply diagnostic text."""
    def __init__(self, folder, nonce):
        self.folder, self.nonce = folder, nonce
        self.started = time.monotonic()
        self.ready_at = None
        self.active = []
        self.calls = []
        self.sequence = 0
        self.publish("boot", timestamp=self.started)

    def publish(self, event, *, active=None, timestamp=None):
        value = dict(format="ultra-workbench-host-progress", version=1, nonce=self.nonce,
            event=event, timestamp=time.monotonic() if timestamp is None else timestamp,
            sequence=0 if active is None else active["sequence"],
            member=None if active is None else active["member"], depth=0 if active is None else active["depth"])
        raw = encode(value)
        if len(raw) > 4096:
            raise ValueError("HOST_PROGRESS_LIMIT")
        # Appending a short complete record permits concurrent Windows readers.
        # Replacing a file while a reader holds it open causes sharing failures.
        with (self.folder / "host-progress.jsonl").open("ab") as stream:
            stream.write(raw)

    def ready(self):
        if self.ready_at is None:
            self.ready_at = time.monotonic()
            self.publish("ready", timestamp=self.ready_at)

    def begin(self, member):
        self.ready()
        self.sequence += 1
        active = dict(sequence=self.sequence, member=member, started=time.monotonic(), depth=len(self.active))
        self.active.append(active)
        self.publish("begin", active=active, timestamp=active["started"])

    def end(self):
        active = self.active.pop()
        self.calls.append(dict(sequence=active["sequence"], member=active["member"], depth=active["depth"],
                               seconds=round(time.monotonic() - active["started"], 9)))
        self.publish("end", active=active)

    def finish(self):
        self.ready()
        self.publish("done")


class PublicLoader(StudentLoader):
    active_component = None

    def component(self, component):
        self.active_component = component
        return super().component(component)

    def _allowed(self, name):
        if name.startswith("src.api."):
            raise ImportBoundaryError("FORBIDDEN_IMPORT")
        return super()._allowed(name)


def signature(callable_, names):
    parameters = inspect.signature(callable_).parameters
    if (tuple(parameters) != tuple(names) or any(p.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD
                                               for p in parameters.values())):
        raise ValueError("CONTRACT_SIGNATURE")


class ProbeTerrain:
    def generate_terrain(self, specification, seed):
        raise ValueError("CONSTRUCTOR_MUST_NOT_GENERATE")


class CallbackProbe:
    """Host adapter records TODOs without adding any student callback."""
    def __init__(self, instance, member):
        self.callback = getattr(instance, member)
        self.member = member
        self.todo = False
        self.diagnostic = None

    def invoke(self, *args):
        began = False
        try:
            if PROGRESS is not None:
                PROGRESS.begin(self.member)
                began = True
            return self.callback(*args)
        except BaseException as exc:
            self.todo = isinstance(exc, NotImplementedError)
            component = {"choose_action": "AgentController", "generate_terrain": "TerrainGenerator",
                         "generate_level": "LevelGenerator"}[self.member]
            self.diagnostic = student_diagnostic(exc, component, self.member)
            raise
        finally:
            if began:
                PROGRESS.end()

    def generate_terrain(self, specification, seed):
        return self.invoke(specification, seed)

    def generate_level(self, specification, seed):
        return self.invoke(specification, seed)

    def choose_action(self, state, agent_id):
        return self.invoke(state, agent_id)


def probe(loader, component):
    forms = {"Character": (("agent_id",), ("explorer",)),
             "Artifact": (("artifact_id", "position", "value"), ("public-artifact", Position(1, 2), 7)),
             "Enemy": (("enemy_id", "position", "encounter_penalty"), ("public-enemy", Position(2, 1), 3)),
             "AgentController": ((), ()), "TerrainGenerator": ((), ()),
             "LevelGenerator": (("terrain_generator",), (ProbeTerrain(),))}
    factory = loader.component(component)
    names, args = forms[component]
    try:
        signature(factory, names)
    except (ValueError, TypeError):
        return dict(status="CONTRACT_FAILURE", code="CONSTRUCTOR_SIGNATURE", component=component)
    instance = factory(*args)
    if component in ("Character", "Artifact", "Enemy"):
        adapter = {"Character": to_character_definition, "Artifact": to_artifact_definition,
                   "Enemy": to_enemy_definition}[component]
        captured = adapter(instance)
        values = ((captured.agent_id,) if component == "Character" else
                  (captured.artifact_id, captured.position, captured.value) if component == "Artifact" else
                  (captured.enemy_id, captured.position, captured.encounter_penalty))
        if values != args:
            return dict(status="CONTRACT_FAILURE", code="INPUT_NOT_PRESERVED", component=component)
    else:
        method, names = {"AgentController": ("choose_action", ("state", "agent_id")),
                        "TerrainGenerator": ("generate_terrain", ("specification", "seed")),
                        "LevelGenerator": ("generate_level", ("specification", "seed"))}[component]
        try:
            signature(getattr(instance, method), names)
        except (ValueError, TypeError, AttributeError):
            return dict(status="CONTRACT_FAILURE", code="PUBLIC_MEMBER_SIGNATURE", component=component)
    return dict(status="OK", code="CONTRACT_SHAPE", component=component,
                behavior="NOT_EXECUTED" if component in ("AgentController", "TerrainGenerator", "LevelGenerator") else "CAPTURED")


def case_entities(loader, level):
    """Capture real case arguments once; no reference entity substitutes."""
    character = to_character_definition(loader.component("Character")(level.character.agent_id))
    if character != level.character:
        raise ValueError("CHARACTER_IDENTITY")
    for artifact in level.artifacts:
        captured = to_artifact_definition(loader.component("Artifact")(
            artifact.artifact_id, artifact.position, artifact.value))
        if captured != artifact:
            raise ValueError("ARTIFACT_IDENTITY")
    for enemy in level.enemies:
        captured = to_enemy_definition(loader.component("Enemy")(
            enemy.enemy_id, enemy.position, enemy.encounter_penalty))
        if captured != enemy:
            raise ValueError("ENEMY_IDENTITY")


def public_terrain_factory(config):
    """Protocol-only public geometry; never provides a route or student source."""
    from src.framework.public_project.catalog import reference_terrain, request
    from src.framework.generation.canonical import terrain_request
    expected = terrain_request(request(config)[0].terrain_spec, 0)["specification"]
    class PublicTerrain:
        def generate_terrain(self, specification, seed):
            if terrain_request(specification, 0)["specification"] != expected:
                raise ValueError("DEPENDENCY_SPECIFICATION")
            return reference_terrain(config, seed)
    return PublicTerrain


def main(folder):
    global PROGRESS, SOURCE_ROOT, SOURCE_MANIFEST
    folder = Path(folder)
    request = read_json((folder / "request.json").read_bytes())
    workspace, manifest = Path(request["workspace"]), request["manifest"]
    result = None
    loader = None
    diagnostic = None
    SOURCE_ROOT, SOURCE_MANIFEST = workspace, manifest
    callback_probes = []
    def context(exc):
        return student_diagnostic(exc, None if loader is None else loader.active_component)
    PROGRESS = HostProgress(folder, request["progress_nonce"]) if request.get("project") is True else None
    try:
        import random
        random.seed(request.get("noise_seed", 1001))
        verify_sources(workspace, manifest)
        loader = PublicLoader(workspace, manifest)
        loader.install()
        operation, payload = request["operation"], request["payload"]
        if operation == "probe":
            result = probe(loader, payload["component"])
        elif operation in {"terrain_v2", "generate_v2", "generation_probe_v2"}:
            from src.framework.public_project.catalog import request as public_request
            from src.framework.generation import canonical
            from src.framework.terrain_generator_execution import execute_terrain_generator_once
            from src.framework.generation.level_execution import execute_level_generator_once, _DependencyObserver
            config = payload["configuration"]
            spec, seed = public_request(config)
            if config["tier"] == 8:
                raise ValueError("PATROL_GENERATION_NOT_SUPPORTED")
            if operation == "generation_probe_v2":
                from src.framework.generation.determinism import run_terrain_session, run_level_session
                alternate_spec, alternate_seed = public_request(payload["alternate"])
                seen = {"terrain": [], "level": []}
                def factory(component, member, kind):
                    def create(*args):
                        instance = loader.component(component)(*args)
                        if any(instance is previous for previous in seen[kind]):
                            raise ValueError("SHARED_INSTANCE")
                        seen[kind].append(instance)
                        adapter = CallbackProbe(instance, member)
                        callback_probes.append(adapter)
                        return adapter
                    return create
                if payload["kind"] == "terrain":
                    session = run_terrain_session(factory("TerrainGenerator", "generate_terrain", "terrain"),
                        canonical.terrain_request(spec.terrain_spec, seed),
                        canonical.terrain_request(alternate_spec.terrain_spec, alternate_seed))
                else:
                    if payload["dependency"] == "reference":
                        # The provider resolves both published requests independently.
                        primary_provider = public_terrain_factory(config)
                        alternate_provider = public_terrain_factory(payload["alternate"])
                        class ReferenceTerrain:
                            def generate_terrain(self, specification, given_seed):
                                chosen = alternate_provider if given_seed >= alternate_seed else primary_provider
                                return chosen().generate_terrain(specification, given_seed)
                        terrain_factory = ReferenceTerrain
                    else:
                        terrain_factory = factory("TerrainGenerator", "generate_terrain", "terrain")
                    session = run_level_session(factory("LevelGenerator", "generate_level", "level"),
                        terrain_factory, canonical.level_request(spec, seed),
                        canonical.level_request(alternate_spec, alternate_seed))
                result = dict(status="OK", session=session)
            elif operation == "terrain_v2":
                terrain = CallbackProbe(loader.component("TerrainGenerator")(), "generate_terrain")
                callback_probes.append(terrain)
                candidate = execute_terrain_generator_once(terrain, spec.terrain_spec, seed)
                result = dict(status="OK", terrain=canonical.terrain_record(candidate))
            else:
                terrain = (public_terrain_factory(config)() if payload["dependency"] == "reference" else
                           CallbackProbe(loader.component("TerrainGenerator")(), "generate_terrain"))
                if isinstance(terrain, CallbackProbe):
                    callback_probes.append(terrain)
                observer = _DependencyObserver(terrain)
                generator = CallbackProbe(loader.component("LevelGenerator")(observer.facade), "generate_level")
                callback_probes.append(generator)
                observer.begin(spec, seed)
                level = execute_level_generator_once(generator, spec, seed)
                observer.active = False
                if not observer.trace or any(item["status"] != "PASS" for item in observer.trace):
                    raise ValueError("TERRAIN_DEPENDENCY_NOT_USED")
                result = dict(status="OK", level=canonical.level_record(level),
                              terrain_calls=len(observer.trace), dependency_trace=observer.snapshot())
        elif operation == "solve_v2":
            from src.framework.public_project.recording import read_level
            from src.framework.public_project.runtime import run_public
            from src.framework.public_practice.records import identity_from_files
            level, config, admission = read_level(payload["level"])
            case_entities(loader, level)
            controller = CallbackProbe(loader.component("AgentController")(), "choose_action")
            callback_probes.append(controller)
            run = run_public(payload["level"], controller,
                identity_from_files({p["path"]: p["sha256"] for p in manifest["sources"]}),
                request["runtime_identity"], payload.get("generation_identity"))
            if run.record_bytes is None:
                raise ValueError(run.code)
            result = dict(status="OK", run=read_json(run.record_bytes), outcome=run.outcome, code=run.code)
        elif operation == "generation_probe":
            from src.framework.public_practice.admission import public_request
            from src.framework.generation.canonical import level_request
            from src.framework.generation.determinism import run_level_session
            requests = [level_request(*public_request(payload[name])) for name in ("primary", "alternate")]
            session = run_level_session(loader.component("LevelGenerator"), loader.component("TerrainGenerator"), *requests)
            if session["status"] != "PASS":
                result = dict(status="CONFORMANCE_FAILURE", code="GENERATION_REPEATABILITY_FAILURE")
            else:
                result = dict(status="OK", session=session)
        elif operation == "generate":
            from src.framework.public_practice.admission import public_request, public_level_record
            from src.framework.generation.level_execution import execute_level_generator_once, _DependencyObserver
            spec, seed = public_request(payload["configuration"])
            terrain = CallbackProbe(loader.component("TerrainGenerator")(), "generate_terrain")
            callback_probes.append(terrain)
            observer = _DependencyObserver(terrain)
            generator = CallbackProbe(loader.component("LevelGenerator")(observer.facade), "generate_level")
            callback_probes.append(generator)
            observer.begin(spec, seed)
            level = execute_level_generator_once(generator, spec, seed)
            if not observer.trace or any(t["status"] != "PASS" for t in observer.trace):
                raise ValueError("TERRAIN_DEPENDENCY_NOT_USED")
            result = dict(status="OK", level=public_level_record(level, payload["configuration"]),
                          terrain_calls=len(observer.trace))
        elif operation == "solve":
            from src.framework.public_practice.admission import read_public_level
            from src.framework.public_practice.runtime import run_public
            from src.framework.public_practice.records import identity_from_files
            level, config = read_public_level(payload["level"])
            character = to_character_definition(loader.component("Character")(level.character.agent_id))
            if character != level.character:
                raise ValueError("CHARACTER_IDENTITY")
            controller = CallbackProbe(loader.component("AgentController")(), "choose_action")
            callback_probes.append(controller)
            run = run_public(level, config, controller,
                identity_from_files({p["path"]: p["sha256"] for p in manifest["sources"]}),
                request["runtime_identity"])
            if run.record_bytes is None:
                raise ValueError(run.code)
            result = dict(status="OK", run=read_json(run.record_bytes), outcome=run.outcome, code=run.code)
        else:
            raise ValueError("UNKNOWN_OPERATION")
        verify_sources(workspace, manifest)
        if loader.policy_violations:
            raise ValueError("CHILD_PROCESS_FORBIDDEN")
    except NotImplementedError as exc:
        diagnostic = context(exc)
        result = dict(status="INCOMPLETE", code="TODO_IMPLEMENTATION")
    except ImportBoundaryError as exc:
        diagnostic = context(exc)
        result = dict(status="IMPORT_FAILURE", code="FORBIDDEN_IMPORT")
    except SubmissionError as exc:
        diagnostic = context(exc)
        result = dict(status="INCOMPLETE", code=exc.code)
    except ContractViolation as exc:
        diagnostic = context(exc)
        result = dict(status="CONTRACT_FAILURE", code="PUBLIC_MEMBER_CONTRACT")
    except GenerationFailure as exc:
        diagnostic = context(exc)
        result = dict(status="CONFORMANCE_FAILURE", code="GENERATION_FAILURE")
    except BaseException as exc:
        diagnostic = context(exc)
        # No student values/reprs or instructor tracebacks enter public output.
        code = exc.code if type(exc) in (LevelExecutionError, TerrainGeneratorExecutionError, PracticeError) else None
        if code is None and type(exc) is ValueError and str(exc) in {
                "TERRAIN_DEPENDENCY_NOT_USED", "CHARACTER_IDENTITY", "CONTRACT_SIGNATURE",
                "CHILD_PROCESS_FORBIDDEN", "ARTIFACT_IDENTITY", "ENEMY_IDENTITY",
                "PATROL_GENERATION_NOT_SUPPORTED"}:
            code = str(exc)
        result = dict(status="CONFORMANCE_FAILURE", code=code or "COMPONENT_EXCEPTION")
    if (any(probe.todo for probe in callback_probes)
            and result.get("code") not in {"SOURCE_DRIFT", "CHILD_PROCESS_FORBIDDEN", "FORBIDDEN_IMPORT"}):
        result = dict(status="INCOMPLETE", code="TODO_IMPLEMENTATION")
    if diagnostic is None:
        diagnostic = next((probe.diagnostic for probe in reversed(callback_probes) if probe.diagnostic), None)
    if diagnostic is not None:
        result["diagnostic"] = diagnostic
    if PROGRESS is not None:
        PROGRESS.finish()
    (folder / "result.json").write_bytes(encode(result))


if __name__ == "__main__":
    main(sys.argv[1])
