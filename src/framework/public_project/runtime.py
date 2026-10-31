"""Active public v2 runtime using the existing static and patrol engines."""
from src.framework.static_execution import run_history as run_static_history
from src.framework.patrol_execution import run_history as run_patrol_history
from .recording import read_level, gameplay, seal_record


def run_public(level_record, controller, source_identity, runtime_identity, generation_identity=None):
    level, config, admission = read_level(level_record)
    policy, _, rules = gameplay(config)
    def build_record(admission, events, frames, summary):
        return seal_record(admission, events, frames, summary, source_identity, runtime_identity, generation_identity)
    if config["rules"]["mode"] == "static":
        return run_static_history(level, config["rules"]["H"], rules["allow_wait"], admission["baseline_cost"],
            policy, admission, controller, build_record)
    return run_patrol_history(level, config["rules"]["H"], rules, admission["baseline_cost"],
        policy, admission, controller, build_record)
