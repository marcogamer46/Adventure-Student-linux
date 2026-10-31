"""Plain-language projections of admitted inputs and finite worker outcomes."""
from src.framework.static_records import read_json

OBJECTS = '''A world has data, decisions, and a runtime that applies those decisions.

Character owns the explorer's agent_id. It does not own the current position. Read the current position from state.agent_position. Artifact owns its artifact_id, position, and value. Enemy owns its enemy_id, position, and encounter_penalty. Preserve each constructor argument and expose it through the matching property. The public adapters copy those objects into independent definition records.

Terrain is the floor plan: dots are traversable cells and hashes are walls. It has no start, exit, rewards, enemies, or controller. TerrainGenerator receives a specification and seed and returns that floor plan. LevelGenerator receives a terrain generator in its constructor. Its generate_level method asks that supplied object for terrain, then assembles a LevelDefinition with the required endpoints, character, and entities. Choosing Provided terrain generator lets you test level assembly before your own terrain generator is ready.

LevelDefinition describes the initial world. WorldSnapshot describes the current read-only state, including agent_position, collected artifacts, and enemy observations. AgentController reads that snapshot and returns a WorldAction. It chooses an intention; the runtime checks and applies it. Your controller does not draw sprites, mutate snapshots, or award points.

A move changes the explorer's position if it is legal. COLLECT names an artifact on the current tile. ENGAGE names a static enemy on an adjacent tile; a successful engagement leaves the explorer where it is. Reaching the exit tile does not finish the attempt: return EXIT there. A patrol has its own published timing rules and cannot be engaged.

Ready-made scenarios need Character, AgentController, and the entities actually present. Both generators can remain unfinished. Terrain generation needs TerrainGenerator. Level generation uses LevelGenerator and its selected terrain provider; AgentController can remain unfinished. After a level is valid, Run solution tests your current controller against that same stored level.

Save your edits before running. Play, Previous, Next, and Replay from start inspect a saved recording. Run solution and Run again start new attempts with your currently saved source.
'''

REPAIR = '''Extract the complete offline project to a writable ordinary folder, then double-click SETUP.cmd using a normal Windows account. It checks every supplied runtime and wheel file and prepares the project's .venv with bundled CPython 3.12.14 for Windows x64, Tk, and Pillow 12.3.0. You do not need an installed Python, internet, or a PowerShell setting.

A successful setup includes a real window check. Open main.py in your IDE and use Run with no arguments, or double-click START.cmd. Select this project's .venv interpreter in the IDE when possible; the launcher can also hand off once to it.

Keep the complete extracted folder together. If the folder moves or a dependency is missing, close the workbench and rerun SETUP.cmd. Existing student source and saved practice history are retained. Extract to a writable folder if setup cannot create its project files.

Keep .setup-payload with the project. Setup checks its files even when an environment or cached wheel already exists. Missing or damaged supplied files cause failure with no download fallback. Obtain and extract the complete original ZIP again, keeping your edited student source and saved practice history.

Both standard and administrator Windows sessions are supported; administrator privileges are not required. If setup refuses the architecture, ownership, or file integrity, use the original supplied package and contact your instructor. If Windows blocks execution, ask your institution's IT team for approval and keep its security policy in place. The workbench does not change system Python, PATH, execution policy, security settings, or course approval. This remains an internal DEVELOPMENT candidate; classroom and art redistribution approvals are pending.
'''


def requirements(selected, *, terrain_only=False):
    config=selected.configuration
    spec=config['specification'];terrain=spec['terrain_spec'];rules=config['rules']
    lines=['Terrain requirements',f"Rows: {terrain['rows']}; columns: {terrain['columns']}.",
        f"Floor cells: {terrain['min_open_tiles']} to {terrain['max_open_tiles']}.",
        'Topology: '+terrain['topology'].replace('_',' ').lower()+'.',
        f"Generation attempts allowed by the specification: {terrain['max_attempts']}.",
        f"Selected seed: {config['seed']}."]
    if terrain_only:return '\n\n'.join(lines)
    lines += ['Level requirements',f"Artifacts required: {spec['artifact_count']}; value range: {spec['artifact_value_min']} to {spec['artifact_value_max']}.",
        f"Enemies required: {spec['enemy_count']}; encounter cost range: {spec['enemy_penalty_min']} to {spec['enemy_penalty_max']}.",
        f"Route moves: {spec['min_route_moves']} to {spec['max_route_moves']}; minimum branch tiles: {spec['min_branch_tiles']}; maximum dead ends: {spec['max_dead_end_tiles']}.",
        f"Alternate path required: {'yes' if spec['require_alternate_path'] else 'no'}. Entity overlap allowed: {'yes' if spec['allow_entity_overlap'] else 'no'}. Entities on endpoints allowed: {'yes' if spec['allow_entities_on_endpoints'] else 'no'}."]
    level=selected.level()
    cell=lambda p:f'row {p.row}, column {p.column}'
    lines += ['This initial world',f'Start: {cell(level.start)}. Exit: {cell(level.exit)}.',
        'Four cardinal moves and explicit EXIT are available. '+('WAIT is allowed.' if rules['allow_wait'] else 'WAIT is not allowed.'),
        f"Action limit: {rules['H']} accepted actions. This is separate from computation timeout."]
    for a in level.artifacts:lines.append(f'Artifact {a.artifact_id}: {cell(a.position)}; value {a.value}. COLLECT targets this ID on its tile.')
    patrols={p.enemy_id:p for p in level.patrols}
    for e in level.enemies:
        if e.enemy_id not in patrols:lines.append(f'Static enemy {e.enemy_id}: {cell(e.position)}; encounter cost {e.encounter_penalty}. ENGAGE from an adjacent tile; engagement does not move the explorer.')
    if patrols:
        lines += [f"Patrol deadline: {rules['D']}. Playback speed does not change logical timing.",
            'Use the complete schedule and action-start occupancy. Patrols cannot be engaged. An accepted EXIT retains the prior patrol clock.']
        for p in level.patrols:lines.append(f'Patrol {p.enemy_id}; initial phase {p.initial_phase}; repeating positions: '+' → '.join(cell(x) for x in p.positions)+'.')
    return '\n\n'.join(lines)


def points(selected):
    data=read_json(selected.raw);policy=data['configuration']['policy'];rules=data['configuration']['rules']
    return (f"Base completion points: {policy['B']}. Points deducted per excess cost unit: {policy['r']}. "
        f"Zero-points threshold: {policy['Q']}. Reference cost without collection: {data['baseline_cost']}.\n\n"
        'Actions taken counts accepted moves, collections, engagements, waiting, and EXIT. Rejected intentions do not increase that count. Encounter cost is the additional declared cost of successful static engagements. Total cost is actions taken plus encounter cost.\n\n'
        'Excess cost is the greater of zero and total cost minus the validated reference cost without collection. Points are zero if completion is absent, if a completed cost is below that verified reference, or if excess cost reaches the zero-points threshold. Otherwise points are the greater of zero and base completion points plus collected artifact points minus the deduction rate times excess cost. There is no upper cap or percentage normalization.\n\n'
        'The threshold does not stop a run. Action limits, patrol deadlines, and computation timeouts are separate. Earned points are shown only for a selected terminal frame or an explicitly opened final result. These are development practice points, not a course grade.')


def blocked_enemy_text(record, frame):
    """Explain action-start occupancy from validated, detached replay facts."""
    delta = {'MOVE_NORTH': (-1, 0), 'MOVE_SOUTH': (1, 0),
             'MOVE_WEST': (0, -1), 'MOVE_EAST': (0, 1)}.get(frame.action)
    fallback = ('The destination was occupied at the start of this action. '
                'Inspect the visible enemies and Scenario rules before choosing a safe action. '
                'The rejected move did not advance the world.')
    if delta is None or not 0 < frame.index < len(record.frames):
        return fallback
    before = record.frames[frame.index - 1]
    destination = (before.position[0] + delta[0], before.position[1] + delta[1])
    occupants = [enemy for enemy in before.enemies if enemy.position == destination]
    if not occupants or any(type(enemy.patrol) is not bool for enemy in occupants):
        return fallback
    patrol = any(enemy.patrol for enemy in occupants)
    static = any(not enemy.patrol for enemy in occupants)
    if patrol and static:
        advice = ('Static enemies and a patrol occupy the destination at action start. '
                  'Legally ENGAGE every remaining static enemy from an adjacent tile; engagement does not move the explorer. '
                  'Patrols cannot be engaged, so clearing static enemies alone does not make this move safe. '
                  'Check the patrol schedule and choose a safe route or wait only where waiting is safe.')
    elif patrol:
        advice = ('A patrol occupies the destination at the start of this action. Patrols cannot be engaged. '
                  'Check its schedule and choose a safe move or wait only where waiting is safe.')
    else:
        advice = ('Static enemies occupy the destination at the start of this action. '
                  'Legally ENGAGE every remaining static enemy on that tile from an adjacent tile before entering. '
                  'Engagement does not move the explorer.')
    return advice + ' The rejected move did not advance the world.'


def playback_feedback(record, frame):
    """Project the selected validated frame, never a future final result."""
    if frame.status == 'RUNNING':
        if frame.position == record.exit:
            return 'At the exit — return EXIT to finish.', 'Arrival is separate from completion. Return EXIT while standing on the exit tile.'
        return None
    if frame.completed:
        return 'Exit reached and accepted', 'The recorded EXIT was accepted and completed the expedition. These are development practice points, not a course grade.'
    if frame.accepted is False:
        body = {'BLOCKED_TERRAIN': 'The requested move points outside the map or into a wall.',
                'NOT_AT_EXIT': 'Return EXIT only while standing on the exit tile.',
                'PATROL_COLLISION': 'The recorded intention was rejected because of patrol occupancy. Inspect the schedule and action-start timing in Scenario rules.',
                'CONTROLLER_ERROR': 'The controller could not provide an accepted action. Review your saved code.'}.get(
                    frame.reason, 'The recorded intention was rejected. Inspect this frame and the scenario rules; no replacement action was supplied.')
        if frame.reason == 'BLOCKED_ENEMY':
            body = blocked_enemy_text(record, frame)
        return 'The action was not accepted', body
    if frame.accepted is True:
        feedback = {
            ('COLLISION', 'PATROL_COLLISION'): ('Run ended — patrol collision',
                'Your last action was allowed, but a patrol moved onto the explorer afterward. '
                'Inspect its schedule and choose a safe move or wait only where waiting is safe.'),
            ('DEADLINE', 'DEADLINE'): ('Deadline reached before EXIT',
                'Your last action was allowed, but the patrol deadline ended this run without an accepted EXIT. '
                'Reaching the exit is separate from returning EXIT within the allowed deadline.'),
            ('TURN_LIMIT', 'MAX_TURNS'): ('Run ended — action limit reached',
                'Your last action was allowed, but the hard limit on accepted actions ended this run without an accepted EXIT. '
                'This limit is separate from the zero-points threshold; the last action was not rejected.')}
        return feedback.get((frame.status, frame.reason), ('Run ended',
            'The saved run ended without completion after an accepted action. Inspect this frame and the scenario rules.'))
    return 'Run ended', 'The saved run ended without an accepted action or completion. Inspect the saved result and your code.'


def failure_text(event):
    code,status,diagnostic=event.get('code'),event.get('status'),event.get('diagnostic')
    if status=='CANCELLED':return 'Run cancelled','The owned attempt has stopped. Run again starts a new attempt.'
    if code=='SOURCE_DRIFT':return 'Code changed during the run','The saved source changed while this attempt was checked. Save your edits, then run again.'
    if status=='RESOURCE':
        limits={'IMPORT_TIMEOUT':'component loading','CALLBACK_TIMEOUT':'one component callback',
            'CONTROLLER_WHOLE_TIMEOUT':'the whole controller run','GENERATION_TIMEOUT':'generation',
            'WORKER_TIMEOUT':'the whole worker'}
        if code in limits:return 'The run did not finish in time','The published time limit for '+limits[code]+' was reached. Review your code, then try again. Support details retains the checked category.'
        return 'The run reached a resource limit','The attempt has stopped. Review output and temporary-file use. Support details retains the checked limit.'
    if event.get('operation') in {'terrain','level'} and code in {
            'INVALID_RETURN','TERRAIN_INVALID','LEVEL_INVALID','TERRAIN_DEPENDENCY_NOT_USED',
            'GENERATOR_REPORTED_FAILURE','GENERATION_FAILURE','GENERATOR_CONTRACT_ERROR'}:
        terrain=event['operation']=='terrain';component='TerrainGenerator' if terrain else 'LevelGenerator'
        detail=('Return a Terrain with the required dimensions, floor count, and topology.' if terrain else
            'Return a LevelDefinition that meets the selected requirements and uses the injected terrain generator.')
        if code=='TERRAIN_DEPENDENCY_NOT_USED':detail='Use the terrain generator supplied to LevelGenerator for this specification and seed.'
        return ('Terrain needs work' if terrain else 'Level needs work'),component+': '+detail+' Open the requirements, save your changes, then generate again.'
    if diagnostic:
        component=diagnostic['component'];member=diagnostic['member']
        context=component+('.'+member if member else '')
        location=diagnostic['file']+(f", line {diagnostic['line']}" if diagnostic['line'] is not None else '')
        if code=='TODO_IMPLEMENTATION':return component+' needs implementation',f'Implement {context} in {location}. Save the file, then run again.'
        if diagnostic['exception_kind'] in {'SyntaxError','IndentationError'}:return 'Your code could not load',f'Syntax error in {location}. Correct the syntax, save the file, then run again.'
        if status=='IMPORT_FAILURE':return 'Your code could not load',f'Review imports for {context} in {location}. Use the public API, standard library, and your selected student helpers.'
        return ('Terrain needs work' if event.get('operation')=='terrain' else 'Level needs work' if event.get('operation')=='level' else 'Your component could not continue'), f'Review {context} in {location}. The checked failure is {diagnostic["exception_kind"]}. Support details contains the bounded category.'
    return 'The environment could not finish the check','Open Setup & repair or ask your instructor for help. This is not a result for your algorithm.'
