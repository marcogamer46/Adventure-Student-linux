"""Finite same-instance and fresh-instance trials around the Task 018 boundary."""

from __future__ import annotations

from src.framework.terrain_generator_execution import (
    TerrainGeneratorExecutionError, execute_terrain_generator_once,
)
from src.framework.terrain_validation import TerrainValidationError
from .canonical import (
    CanonicalError, canonical_bytes, digest, read_terrain_request,
    terrain_record, terrain_request,
)

TRIAL_LAYOUT = (("A1", "A", 0), ("A2", "A", 0), ("B", "B", 0),
                ("A3", "A", 0), ("A4", "A", 1))
CATEGORIES = frozenset({"SUCCESS", "HOST_INPUT", "COMPONENT_CONTRACT",
                        "COMPONENT_FAILURE", "INVALID_OUTPUT", "NONDETERMINISM",
                        "FACTORY_SETUP", "DEPENDENCY_FAILURE"})
CODES = frozenset({"OK", "INVALID_REQUEST", "FACTORY_NOT_CALLABLE", "FACTORY_EXCEPTION",
                   "SHARED_INSTANCE", "GENERATOR_CONTRACT_ERROR",
                   "GENERATOR_REPORTED_FAILURE", "GENERATOR_EXCEPTION", "INVALID_RETURN",
                   "TERRAIN_INVALID", "CONTENT_MISMATCH", "INVALID_SPECIFICATION",
                   "INVALID_SEED", "CONTRADICTORY_SPECIFICATION", "LEVEL_INVALID",
                   "DEPENDENCY_SPECIFICATION", "DEPENDENCY_SEED", "DEPENDENCY_BUDGET",
                   "DEPENDENCY_DURING_CONSTRUCTION", "DEPENDENCY_FACTORY_EXCEPTION",
                   "SHARED_DEPENDENCY"})
STAGES = frozenset({"factory", "terrain-input", "terrain-execution",
                    "terrain-validation", "comparison", "level-input", "level-execution",
                    "level-validation", "terrain-dependency", "dependency-construction",
                    "level-patrol", "level-placement", "level-range", "level-inventory",
                    "level-identity", "level-shape", "level-route"})
DETAIL_CODES = frozenset({"WRONG_TYPE", "INVALID_SPECIFICATION", "INVALID_TERRAIN",
                         "DIMENSION_MISMATCH", "OPEN_COUNT_OUT_OF_RANGE", "DISCONNECTED",
                         "TOPOLOGY_MISMATCH", "INVALID_PROVENANCE", "PLACEMENT_INVALID",
                         "INVALID_LEVEL", "PATROLS_NOT_ALLOWED", "INVALID_PATROL",
                         "UNKNOWN_PATROL_ENEMY", "DUPLICATE_PATROL_ENEMY", "PATROL_NOT_TRAVERSABLE",
                         "INVALID_PATROL_STEP", "PATROL_INITIAL_POSITION_MISMATCH", "RANGE_INVALID",
                         "INVALID_ARTIFACT", "INVALID_ENEMY", "ARTIFACT_NOT_TRAVERSABLE",
                         "ENEMY_NOT_TRAVERSABLE", "ENEMY_ON_START", "ENTITY_ON_ENDPOINT", "ENTITY_OVERLAP",
                         "INVENTORY_INVALID", "ARTIFACT_VALUE_OUT_OF_RANGE", "ENEMY_PENALTY_OUT_OF_RANGE",
                         "IDENTITY_INVALID", "ARTIFACT_COUNT_MISMATCH", "ENEMY_COUNT_MISMATCH",
                         "DUPLICATE_ENTITY_ID", "INVALID_ORIGINAL_SEED", "LEVEL_ID_MISMATCH",
                         "PROFILE_ID_MISMATCH", "AGENT_ID_MISMATCH", "SEED_MISMATCH", "SHAPE_INVALID",
                         "ROUTE_INVALID", "BRANCH_COUNT_BELOW_MINIMUM", "DEAD_END_COUNT_ABOVE_MAXIMUM",
                         "ALTERNATE_PATH_REQUIRED", "TERRAIN_INVALID", "ENDPOINTS_NOT_DISTINCT",
                         "ENDPOINT_NOT_TRAVERSABLE", "PATH_ENDPOINT_MISMATCH", "ROUTE_DISTANCE_OUT_OF_RANGE",
                         "NO_ROUTE"})


def _trial(layout: tuple, *, invoked: bool, category: str, code: str,
           stage: str, detail_code: str | None = None, candidate: dict | None = None) -> dict:
    # invoked means the single-call execution boundary was attempted. A member
    # contract failure can occur before the documented method itself is called.
    label, request, instance = layout
    return dict(trial=label, request=request, instance=instance, invoked=invoked,
                status="PASS" if category == "SUCCESS" else "FAIL", category=category,
                code=code, stage=stage, detail_code=detail_code, candidate=candidate,
                digest=digest(candidate) if candidate is not None else None)


def _diagnostic(error: TerrainGeneratorExecutionError) -> tuple[str, str, str | None]:
    code = error.code
    if code == "GENERATOR_CONTRACT_ERROR":
        return "COMPONENT_CONTRACT", "terrain-execution", None
    if code in ("GENERATOR_REPORTED_FAILURE", "GENERATOR_EXCEPTION"):
        return "COMPONENT_FAILURE", "terrain-execution", None
    if code == "INVALID_RETURN":
        return "INVALID_OUTPUT", "terrain-execution", None
    if code == "TERRAIN_INVALID":
        # Only inspect an owned exact validator exception. Never stringify or
        # traverse arbitrary component exceptions that happen to be its context.
        nested = BaseException.__context__.__get__(error)
        detail = None
        if type(nested) is TerrainValidationError:
            value = nested.code
            if type(value) is str and value in DETAIL_CODES:
                detail = value
        return "INVALID_OUTPUT", "terrain-validation", detail
    return "HOST_INPUT", "terrain-input", None


def run_terrain_session(factory: object, primary: dict, alternate: dict) -> dict:
    """Execute A/A/B/A on one object, then A on a genuinely different object.

    Freeze both host requests before constructing components. A factory is
    trusted setup; ordinary constructor errors are bounded and BaseException
    cancellation/termination is allowed to reach the worker infrastructure.
    Every scheduled call has evidence, including calls prevented by setup.
    """
    report = dict(kind="terrain-session", status="FAIL", category="HOST_INPUT",
                  code="INVALID_REQUEST", stage="terrain-input", detail_code=None,
                  fresh_instance=False, comparison="INCOMPLETE", trials=[])
    try:
        requests = {
            "A": terrain_request(*read_terrain_request(primary)),
            "B": terrain_request(*read_terrain_request(alternate)),
        }
        if canonical_bytes(requests["A"]) == canonical_bytes(requests["B"]):
            return report
    except CanonicalError:
        return report
    trials = report["trials"]
    first_instance = None
    first_constructed = False
    first_valid_bytes = None
    mismatch = False
    for instance in (0, 1):
        layouts = [item for item in TRIAL_LAYOUT if item[2] == instance]
        setup_code = None
        generator = None
        if not callable(factory):
            setup_code = "FACTORY_NOT_CALLABLE"
        else:
            try:
                generator = factory()
            except Exception:
                setup_code = "FACTORY_EXCEPTION"
        if setup_code is None:
            if instance == 0:
                first_instance = generator
                first_constructed = True
            elif first_constructed and generator is first_instance:
                setup_code = "SHARED_INSTANCE"
            elif first_constructed:
                report["fresh_instance"] = True
        if setup_code is not None:
            trials.extend(_trial(layout, invoked=False, category="FACTORY_SETUP",
                                 code=setup_code, stage="factory") for layout in layouts)
            continue
        for layout in layouts:
            specification, seed = read_terrain_request(requests[layout[1]])
            try:
                accepted = execute_terrain_generator_once(generator, specification, seed)
            except TerrainGeneratorExecutionError as error:
                category, stage, detail = _diagnostic(error)
                code = error.code if error.code in CODES else "INVALID_REQUEST"
                trials.append(_trial(layout, invoked=True, category=category, code=code,
                                     stage=stage, detail_code=detail))
                continue
            candidate = terrain_record(accepted)
            content = canonical_bytes(candidate)
            trials.append(_trial(layout, invoked=True, category="SUCCESS", code="OK",
                                 stage="terrain-validation", candidate=candidate))
            if layout[1] == "A":
                if first_valid_bytes is None:
                    first_valid_bytes = content
                elif content != first_valid_bytes:
                    mismatch = True
    failed = next((trial for trial in trials if trial["status"] != "PASS"), None)
    if mismatch:
        report.update(category="NONDETERMINISM", code="CONTENT_MISMATCH",
                      stage="comparison", comparison="MISMATCH")
    elif failed is not None:
        report.update({key: failed[key] for key in ("category", "code", "stage", "detail_code")})
    else:
        report.update(status="PASS", category="SUCCESS", code="OK",
                      stage="comparison", comparison="MATCH")
    return report


def run_level_session(factory: object, terrain_factory: object, primary: dict, alternate: dict) -> dict:
    """Run a finite full-content level sequence for one dependency pairing.

    Both original requests are frozen/preflighted before either factory. A
    genuinely new pair requires a different assembler and a different provider,
    not merely a new observer around a shared provider. No terrain is generated
    unless the assembler invokes the one documented dependency method.
    """
    # Level-only validator imports do not enter cold terrain execution.
    from .canonical import level_record, level_request, read_level_request
    from .level_execution import (
        LevelExecutionError, _DependencyObserver, execute_level_generator_once,
        preflight_level_request,
    )

    report = dict(kind="level-session", status="FAIL", category="HOST_INPUT",
                  code="INVALID_REQUEST", stage="level-input", detail_code=None,
                  fresh_instance=False, comparison="INCOMPLETE", trials=[])
    try:
        requests = {}
        for label, value in (("A", primary), ("B", alternate)):
            spec, seed = preflight_level_request(*read_level_request(value))
            requests[label] = level_request(spec, seed)
        if canonical_bytes(requests["A"]) == canonical_bytes(requests["B"]):
            return report
    except CanonicalError:
        return report
    except LevelExecutionError as error:
        report.update(code=error.code, stage=error.stage, detail_code=error.detail_code)
        return report

    def level_trial(layout, *, trace=None, **fields):
        entry = _trial(layout, **fields)
        entry["dependency_trace"] = [] if trace is None else trace
        return entry

    first_provider = first_generator = None
    first_provider_exists = first_generator_exists = False
    first_valid_bytes = None
    mismatch = False
    trials = report["trials"]
    for instance in (0, 1):
        layouts = [item for item in TRIAL_LAYOUT if item[2] == instance]
        observer = None
        setup_code = None
        setup_category, setup_stage = "FACTORY_SETUP", "factory"
        if not callable(terrain_factory) or not callable(factory):
            setup_code = "FACTORY_NOT_CALLABLE"
        else:
            try:
                provider = terrain_factory()
            except Exception:
                setup_code = "DEPENDENCY_FACTORY_EXCEPTION"
            else:
                if instance == 0:
                    first_provider, first_provider_exists = provider, True
                elif first_provider_exists and provider is first_provider:
                    setup_code = "SHARED_DEPENDENCY"
                if setup_code is None:
                    observer = _DependencyObserver(provider)
                    try:
                        generator = factory(observer.facade)
                    except Exception:
                        setup_code = "FACTORY_EXCEPTION"
                    if observer.trace:
                        setup_code = "DEPENDENCY_DURING_CONSTRUCTION"
                        setup_category, setup_stage = "DEPENDENCY_FAILURE", "dependency-construction"
                    elif setup_code is None:
                        if instance == 0:
                            first_generator, first_generator_exists = generator, True
                        elif first_generator_exists and generator is first_generator:
                            setup_code = "SHARED_INSTANCE"
                        elif first_generator_exists and first_provider_exists:
                            report["fresh_instance"] = True
        if setup_code is not None:
            for layout in layouts:
                trials.append(level_trial(layout, invoked=False, category=setup_category,
                              code=setup_code, stage=setup_stage,
                              trace=observer.snapshot() if observer is not None else []))
            continue
        for layout in layouts:
            spec, seed = read_level_request(requests[layout[1]])
            observer.begin(spec, seed)
            failure = None
            try:
                candidate = execute_level_generator_once(generator, spec, seed)
            except LevelExecutionError as error:
                failure = error
            finally:
                observer.active = False
            trace = observer.snapshot()
            dependency_failure = next((entry for entry in trace if entry["status"] != "PASS"), None)
            if dependency_failure is not None:
                trials.append(level_trial(layout, invoked=True, category="DEPENDENCY_FAILURE",
                              code=dependency_failure["code"], stage=dependency_failure["stage"],
                              detail_code=dependency_failure["detail_code"], trace=trace))
                continue
            if failure is not None:
                if failure.code == "GENERATOR_CONTRACT_ERROR":
                    category = "COMPONENT_CONTRACT"
                elif failure.code in {"GENERATOR_REPORTED_FAILURE", "GENERATOR_EXCEPTION"}:
                    category = "COMPONENT_FAILURE"
                elif failure.code in {"INVALID_RETURN", "LEVEL_INVALID"}:
                    category = "INVALID_OUTPUT"
                else:
                    category = "HOST_INPUT"
                trials.append(level_trial(layout, invoked=True, category=category, code=failure.code,
                              stage=failure.stage, detail_code=failure.detail_code, trace=trace))
                continue
            record = level_record(candidate)
            content = canonical_bytes(record)
            trials.append(level_trial(layout, invoked=True, category="SUCCESS", code="OK",
                          stage="level-validation", candidate=record, trace=trace))
            if layout[1] == "A":
                if first_valid_bytes is None:
                    first_valid_bytes = content
                elif content != first_valid_bytes:
                    mismatch = True
    failed = next((trial for trial in trials if trial["status"] != "PASS"), None)
    if mismatch:
        report.update(category="NONDETERMINISM", code="CONTENT_MISMATCH",
                      stage="comparison", comparison="MISMATCH")
    elif failed is not None:
        report.update({key: failed[key] for key in ("category", "code", "stage", "detail_code")})
    else:
        report.update(status="PASS", category="SUCCESS", code="OK",
                      stage="comparison", comparison="MATCH")
    return report
