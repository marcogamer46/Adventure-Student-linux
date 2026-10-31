"""Active exact baseline preparation, separate from passive public record reads."""
from src.framework.generation import canonical
from src.framework.public_practice.admission import PracticeError
from src.framework.baseline.static.values import SearchBudget, StaticRules
from src.framework.baseline.static.search import certify_static
from src.framework.baseline.patrol.values import PatrolRules
from src.framework.baseline.patrol.search import certify_patrol
from .recording import LEVEL_FORMAT, VERSION, SCOPE, gameplay, proof_record, read_level
from .catalog import validate_configuration, request


def prepare_level(level, config, *, budget=SearchBudget()):
    config = validate_configuration(config)
    spec, seed = request(config)
    policy, pd, rules = gameplay(config)
    mode = config["rules"]["mode"]
    if mode == "static":
        result = certify_static(level, spec, seed, rules=StaticRules(rules["allow_wait"]), budget=budget)
    else:
        result = certify_patrol(level, spec, seed, rules=PatrolRules(**rules), budget=budget)
    if result.outcome != "CERTIFIED":
        error = PracticeError(result.code)
        error.status = result.outcome
        raise error
    record = dict(format=LEVEL_FORMAT, version=VERSION, scope=SCOPE, configuration=config,
        level=canonical.level_record(level), request=canonical.level_request(spec, seed),
        rules=rules, policy=pd, baseline_cost=result.baseline_cost,
        proof=proof_record(result.certificate, mode, rules))
    read_level(record)
    return record
