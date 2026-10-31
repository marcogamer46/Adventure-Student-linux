"""Published finite Adventure families and examples, independent of instructors.

Generated candidates are judged against the original specification, never map
equality. All nine tiers are available. Tier 8 adds supplied patrol controller
worlds and retains every static 0–7 T/G/I category without patrol generation.
"""
import json
from src.api import (ArtifactDefinition, CharacterDefinition, EnemyDefinition,
    LevelDefinition, LevelSpecification, PatrolDefinition, Position, Terrain,
    TerrainGenerationSpec, TerrainTopology)
from src.framework.generation import canonical

FORMAT = "ultra-project-configuration"
VERSION = 2
SCOPE = "public-development"
FIELDS = {"format", "version", "scope", "scenario_id", "tier", "seed", "overrides", "specification", "rules", "policy"}


class CatalogError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


# tier, variant, label, grid, start, exit, artifacts, enemies, patrols, H, D
# Finite development instances; they do not approve classroom grading numbers.
_EXAMPLES = (
    (0,"A","Straight horizontal passage",(".....",),(0,0),(0,4),(),(),(),32,None),
    (0,"B","Straight vertical passage",(".",)*7,(0,0),(6,0),(),(),(),40,None),
    (1,"A","Bent passage east then south",("....","###.","###."),(0,0),(2,3),(),(),(),40,None),
    (1,"B","Bent passage with several turns",("..##","#.##","#..."),(0,0),(2,3),(),(),(),40,None),
    (2,"A","Branching tree with four leaves",("##.##",".....","##.##","##.##"),(1,0),(3,2),(),(),(),48,None),
    (2,"B","Branching tree with a longer detour",("#.###",".....","#.###","#...."),(1,4),(3,4),(),(),(),64,None),
    (3,"A","Cycle with two endpoint routes",("....",".##.","...."),(0,0),(2,3),(),(),(),64,None),
    (3,"B","Connected general terrain",("....",)*3,(0,0),(2,3),(),(),(),72,None),
    (4,"A","Optional valuable and costly artifacts",("....",".##.","...."),(0,0),(2,3),((0,2,25),(2,0,1)),(),(),72,None),
    (4,"B","Artifact decisions with alternate routes",("....",)*3,(0,0),(2,3),((0,2,24),(2,1,3)),(),(),80,None),
    (5,"A","Avoidable enemy penalties",("....",".##.","...."),(0,0),(2,3),(),((0,1,6),(2,2,2)),(),88,None),
    (5,"B","Unavoidable co-located blockers",(".####","....."),(0,0),(1,4),(),((1,2,7),(1,2,3)),(),88,None),
    (6,"A","Mixed rewards and enemy tradeoffs",(".....",)*3,(1,0),(1,4),((0,2,35),(2,2,1)),((0,2,8),(1,2,3)),(),112,None),
    (6,"B","Mixed routes near the scoring cutoff",("......",".####.","......"),(0,0),(2,5),((2,2,40),(0,3,2)),((2,2,5),(0,2,10)),(),112,None),
    (7,"A","Larger combined world",("..........",)*8,(3,0),(3,9),((0,4,35),(7,7,6),(4,4,2)),((3,4,7),(3,5,4),(4,4,8)),(),512,None),
    (7,"B","Scaled combined world",("............",)*10,(4,0),(4,11),((0,5,40),(9,5,7),(4,3,2)),((4,5,9),(3,5,4),(5,5,6)),(),768,None),
    (8,"A","Visible patrol with repeated positions",(".....",)*2,(0,0),(0,4),((1,4,20),),((0,2,5),(1,3,2)),((0,((0,2),(0,2),(1,2),(1,1),(0,1)),0),),32,24),
    (8,"B","Visible patrol with a nonzero phase",(".....",)*3,(1,0),(1,4),((2,3,30),),((0,2,6),(2,2,4)),((0,((1,2),(0,2),(0,3),(1,3),(1,2)),1),),40,28),
)


# Additional Task 037 teaching inputs have distinct identities and do not alter
# the historical eighteen-family assessment matrix returned by public_cases.
_TEACHING_EXAMPLES = (
    (4,"GUIDE-PATH-ARTIFACT","Path with artifacts",(".....",),(0,0),(0,4),((0,2,20),),(),(),40,None),
    (4,"GUIDE-BEND-ARTIFACT","Bent path with artifacts",("....","###.","###."),(0,0),(2,3),((0,2,20),),(),(),48,None),
    (5,"GUIDE-PATH-ENEMY","Path with an enemy",(".....",),(0,0),(0,4),(),((0,2,6),),(),48,None),
    (5,"GUIDE-ENEMY-CHOICE","Short route with an enemy or longer route without one",("....",".##.","...."),(0,0),(0,2),(),((0,1,6),),(),64,None),
)


def _identity(example):
    if example[1].startswith("GUIDE-"):
        return "ADV-037-" + example[1][6:] + "-DEV"
    return f"ADV-T{example[0]}-{example[1]}-DEV"


def _example(identity):
    if type(identity) is not str:
        raise CatalogError("UNSUPPORTED_CHALLENGE")
    found = next((item for item in _EXAMPLES + _TEACHING_EXAMPLES if _identity(item) == identity), None)
    if found is None:
        raise CatalogError("UNSUPPORTED_CHALLENGE")
    return found


def _spec(example):
    tier, variant, _, rows, _, _, artifacts, enemies, _, H, _ = example
    count = sum(row.count(".") for row in rows)
    topology = {0: TerrainTopology.STRAIGHT_PATH, 1: TerrainTopology.BENT_PATH,
                2: TerrainTopology.BRANCHING_TREE}.get(tier, TerrainTopology.GENERAL)
    teaching = variant.startswith("GUIDE-")
    if teaching:
        topology = {"GUIDE-PATH-ARTIFACT": TerrainTopology.STRAIGHT_PATH,
                    "GUIDE-BEND-ARTIFACT": TerrainTopology.BENT_PATH,
                    "GUIDE-PATH-ENEMY": TerrainTopology.STRAIGHT_PATH}.get(variant, TerrainTopology.GENERAL)
    simple_path = tier < 2 or (teaching and variant != "GUIDE-ENEMY-CHOICE")
    return LevelSpecification(level_id=f"adventure-t{tier}-{variant.lower()}", profile_id=_identity(example), agent_id="explorer",
        terrain_spec=TerrainGenerationSpec(rows=len(rows), columns=len(rows[0]), min_open_tiles=3*count//4 if tier == 7 else count,
            max_open_tiles=count, max_attempts=3, topology=topology), artifact_count=len(artifacts), enemy_count=len(enemies),
        artifact_value_min=max((p[2] for p in artifacts), default=0) if teaching else 0, artifact_value_max=max((p[2] for p in artifacts), default=0),
        enemy_penalty_min=max((p[2] for p in enemies), default=0) if teaching else 0, enemy_penalty_max=max((p[2] for p in enemies), default=0),
        min_route_moves=count-1 if simple_path else 1, max_route_moves=count-1,
        min_branch_tiles=1 if tier == 2 else 0, max_dead_end_tiles=count, require_alternate_path=tier == 3,
        allow_entity_overlap=tier >= 5 and not teaching, allow_entities_on_endpoints=False, max_turns=H, max_attempts=3)


def tuning(challenge):
    """Concrete unapproved development proposal, derived from finite graph size.

    A two-sweep/backtrack allowance remains below Q and has positive completion
    credit. H includes additional sweeps beyond that cutoff. D is separate and
    is certified under the visible patrol schedule during preparation.
    """
    item = _example(challenge)
    spec = _spec(item)
    tiles = spec.terrain_spec.max_open_tiles
    penalties = spec.enemy_count * spec.enemy_penalty_max
    teaching_excess_bound = 2 * tiles + spec.artifact_count + spec.enemy_count + penalties
    margin = max(4, tiles // 2)
    Q = teaching_excess_bound + margin
    r = 5
    B = max(100, r * teaching_excess_bound + 25)
    return dict(status="DEVELOPMENT_PROPOSAL_NOT_COURSE_APPROVED", accessible_tiles=tiles,
        teaching_excess_bound=teaching_excess_bound, cost_margin=margin, B=B, r=r, Q=Q,
        H=item[9], D=item[10], reasoning="Two graph sweeps plus one-time entity costs and positive margin; exact minimum remains level-specific.")


def _make(challenge, seed, overrides):
    example = _example(challenge)
    if type(seed) is not int or not 0 <= seed <= 2**31-1:
        raise CatalogError("INVALID_SEED")
    if overrides is None:
        overrides = {}
    if (type(overrides) is not dict or set(overrides)-{"reverse"}
            or any(type(key) is not str for key in overrides) or type(overrides.get("reverse", False)) is not bool):
        raise CatalogError("HOST_CONFIGURATION")
    reverse = overrides.get("reverse", False)
    if example[0] == 8 and reverse:
        raise CatalogError("HOST_CONFIGURATION")
    spec, values = _spec(example), tuning(challenge)
    return dict(format=FORMAT, version=VERSION, scope=SCOPE, scenario_id=challenge, tier=example[0], seed=seed,
        overrides={"reverse":reverse}, specification=canonical.level_request(spec, seed)["specification"],
        rules=dict(mode="patrol" if example[0] == 8 else "static", H=example[9], D=example[10], allow_wait=True),
        policy=dict(policy_id="DEV-ADVENTURE-FAMILY-B-V2", B=values["B"], r=values["r"], Q=values["Q"]))


def configuration(challenge, seed, overrides=None):
    return _make(challenge, seed, overrides)


def validate_configuration(config):
    if type(config) is not dict or set(config) != FIELDS:
        raise CatalogError("HOST_CONFIGURATION")
    expected = _make(config["scenario_id"], config["seed"], config["overrides"])
    try:
        if json.dumps(config, sort_keys=True, separators=(",",":"), allow_nan=False) != json.dumps(expected, sort_keys=True, separators=(",",":"), allow_nan=False):
            raise CatalogError("HOST_CONFIGURATION")
    except (TypeError, ValueError):
        raise CatalogError("HOST_CONFIGURATION") from None
    return expected


def request(config):
    config = validate_configuration(config)
    return canonical.read_level_request(dict(format=canonical.FORMAT, version=canonical.VERSION,
        kind="level-request", specification=config["specification"], seed=config["seed"]))


def reference_terrain(config, seed):
    config = validate_configuration(config)
    if type(seed) is not int or not 0 <= seed <= 2**31-1:
        raise CatalogError("INVALID_SEED")
    return Terrain(_example(config["scenario_id"])[3])


def validate_family_endpoints(level, tier):
    """The published tree family adds a leaf rule to generic v1 bounds."""
    if tier == 2:
        for endpoint in (level.start, level.exit):
            degree = sum(level.terrain.is_traversable(Position(endpoint.row+dr, endpoint.column+dc))
                         for dr,dc in ((-1,0),(1,0),(0,-1),(0,1)))
            if degree != 1:
                raise CatalogError("TREE_ENDPOINT_NOT_LEAF")


def example_level(config):
    config = validate_configuration(config)
    example = _example(config["scenario_id"])
    spec, seed = request(config)
    start, end = example[4:6]
    if config["overrides"]["reverse"]:
        start, end = end, start
    return LevelDefinition(level_id=spec.level_id, profile_id=spec.profile_id, seed=seed,
        terrain=Terrain(example[3]), start=Position(*start), exit=Position(*end), character=CharacterDefinition(spec.agent_id),
        artifacts=tuple(ArtifactDefinition(f"artifact-{i}", Position(r,c),v) for i,(r,c,v) in enumerate(example[6])),
        enemies=tuple(EnemyDefinition(f"enemy-{i}", Position(r,c),p) for i,(r,c,p) in enumerate(example[7])),
        patrols=tuple(PatrolDefinition(enemy_id=f"enemy-{i}", positions=tuple(Position(*p) for p in positions), initial_phase=phase)
            for i,positions,phase in example[8]))


def list_challenges():
    return tuple(dict(scenario_id=_identity(item), challenge=_identity(item), tier=item[0], label=item[2],
        mode="patrol" if item[0] == 8 else "static", family=_spec(item).terrain_spec.topology.value,
        public_seeds=[11,29], generation_supported=item[0] != 8, development_only=True,
        specification=canonical.level_request(_spec(item), 11)["specification"],
        rules=configuration(_identity(item),11)["rules"], policy=configuration(_identity(item),11)["policy"],
        tuning=tuning(_identity(item)), allowed_overrides={"reverse":"boolean"} if item[0] != 8 else {},
        required_endpoint_rule="leaves" if item[0] == 2 else "original specification",
        description="Published DEVELOPMENT family; valid generated maps may differ.") for item in _EXAMPLES)


def public_cases():
    cases = []
    for challenge in list_challenges():
        for seed in challenge["public_seeds"]:
            config = configuration(challenge["scenario_id"], seed, {"reverse":seed == 29 and challenge["tier"] != 8})
            definitions = [("C",None)] if challenge["tier"] == 8 else [("T",None),("G","reference"),("G","student"),("C",None),("I",None)]
            for lane, dependency in definitions:
                suffix = "-"+dependency if dependency else ""
                value = dict(case_id=f"{challenge['scenario_id']}-{seed}-{lane}{suffix}", scenario_id=challenge["scenario_id"],
                    tier=challenge["tier"], lane=lane, dependency=dependency, configuration=config)
                if lane == "C":
                    value["level"] = canonical.level_record(example_level(config))
                cases.append(value)
    return tuple(cases)


def teaching_challenges():
    """Explicit additional public practice; never appended to grading cases."""
    return tuple(dict(scenario_id=_identity(item), label=item[2], public_seeds=[11],
                      generation_supported=True, development_only=True) for item in _TEACHING_EXAMPLES)
