"""Public analytic admission wrapper for the shared static execution engine."""
from src.framework.static_execution import run_history
from src.framework.generated_static.values import StaticRun
from .admission import POLICY, PracticeError, admit_public, validate_config
from .records import admission_record, seal_public_record, validate_identity


def run_public(level, config, controller, source_identity, runtime_identity):
    try:
        config = validate_config(config)
        source_identity, runtime_identity = validate_identity(source_identity), validate_identity(runtime_identity)
    except Exception as error:
        return StaticRun("HOST_ERROR", getattr(error, "code", "HOST_CONFIGURATION"))
    try:
        owned, spec, baseline = admit_public(level, config)
        admission = admission_record(owned, config)
    except PracticeError as error:
        return StaticRun("INVALID_INPUT", error.code)
    try:
        def build(admission, events, frames, summary):
            return seal_public_record(admission, events, frames, summary, source_identity, runtime_identity)
        return run_history(owned, spec.max_turns, config["allow_wait"], baseline, POLICY,
                           admission, controller, build)
    except Exception:
        return StaticRun("HOST_ERROR", "EXECUTION_ERROR")
