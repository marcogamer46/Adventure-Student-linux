"""Format-neutral passive patrol history checks; no search or execution imports."""
from src.api import EnemyObservation, Position, WorldActionType, WorldSnapshot
from src.framework.generation import canonical
from src.framework.static_records import (ReplayError, ReplayView, _action, _keys, encode, frame_record as public_frame_record)
from src.framework.patrol_values import event_metrics
from src.framework.generated_static.values import WORKER_FAILURE_CODES, SETUP_FAILURE_CODES, CALLBACK_FAILURE_CODES
MOVES={"MOVE_NORTH":(-1,0),"MOVE_SOUTH":(1,0),"MOVE_WEST":(0,-1),"MOVE_EAST":(0,1)}
EVENT_FIELDS=("attempt","accepted","code","action","turn_before","turn_after","position_before","position_after",
    "artifact_reward","encounter_penalty","collected_artifact_id","defeated_enemy_id","patrol_turn_before",
    "patrol_turn_after","order","terminal")

def timing(value,cap):
    value=_keys(value,("allow_wait","allow_collect","allow_engage","deadline_turn"))
    if (any(type(value[k]) is not bool for k in ("allow_wait","allow_collect","allow_engage"))
            or (value['deadline_turn'] is not None and (type(value['deadline_turn']) is not int or not 0<value['deadline_turn']<cap))):
        raise ReplayError("INVALID_TIMING")
    return dict(value)


def allowed_actions(rules):
    return tuple(k for k in WorldActionType if k is not WorldActionType.INTERACT
        and (rules['allow_wait'] or k is not WorldActionType.WAIT)
        and (rules['allow_collect'] or k is not WorldActionType.COLLECT)
        and (rules['allow_engage'] or k is not WorldActionType.ENGAGE))


def snapshot(level,policy,baseline,cap,rules,position,turn,collected,defeated,phase_turn):
    owned=canonical.read_level(canonical.level_record(level));patrols={p.enemy_id:p for p in owned.patrols}
    observations=[]
    for e in owned.enemies:
        p=patrols.get(e.enemy_id)
        phase=None if p is None else (p.initial_phase+phase_turn)%p.period
        pos=(None if e.enemy_id in defeated else e.position) if p is None else p.positions[phase]
        observations.append(EnemyObservation(enemy_id=e.enemy_id,position=pos,phase=phase))
    return WorldSnapshot(level=owned,agent_position=Position(*position),turn=turn,
        collected_artifact_ids=tuple(sorted(collected)),defeated_enemy_ids=tuple(sorted(defeated)),
        base_points=policy.base_points,deduction_rate=policy.deduction_rate,baseline_cost=baseline,
        zero_score_excess=policy.zero_score_excess,max_turns=cap,deadline_turn=rules['deadline_turn'],
        allowed_actions=allowed_actions(rules),enemy_observations=tuple(observations))


def frame_record(frame,phase_turn):return {**public_frame_record(frame),'patrol_turn':phase_turn}


def _event(event,index,level,rules,cap,position,turn,phase_turn,collected,defeated):
    """Independently rebuild stored evidence, never invoking a runtime transition."""
    event=_keys(event,EVENT_FIELDS);action=None if event['action'] is None else _action(event['action'])
    destination,reward,penalty,artifact,enemy,completed=position,0,0,None,None,False
    order=['observe','callback'];terminal=None
    schedules={p.enemy_id:p for p in level.patrols}
    if action is None:
        code=event['code']
        if type(code) is not str or (code!='MALFORMED_ACTION' and code not in CALLBACK_FAILURE_CODES):
            raise ReplayError("INVALID_EVENT")
        if (code=='CONTROLLER_CONTRACT' or code in SETUP_FAILURE_CODES) and index!=1:
            raise ReplayError("INVALID_EVENT")
        if code=='MALFORMED_ACTION':order.append('validate')
    else:
        order.append('validate');kind,target=action.action_type.value,action.target_id
        if action.action_type not in allowed_actions(rules):code='ACTION_DISABLED'
        elif kind not in ('COLLECT','ENGAGE') and target is not None:code='UNEXPECTED_TARGET'
        elif kind in MOVES:
            dr,dc=MOVES[kind];candidate=(position[0]+dr,position[1]+dc)
            occupied={(e.position.row,e.position.column) for e in level.enemies if e.enemy_id not in schedules and e.enemy_id not in defeated}
            for p in schedules.values():
                pos=p.positions[(p.initial_phase+phase_turn)%len(p.positions)];occupied.add((pos.row,pos.column))
            if not level.terrain.is_traversable(Position(*candidate)):code='BLOCKED_TERRAIN'
            elif candidate in occupied:code='BLOCKED_ENEMY'
            else:code,destination='OK',candidate
        elif kind=='COLLECT':
            found=next((a for a in level.artifacts if a.artifact_id==target and target not in collected
                        and (a.position.row,a.position.column)==position),None)
            if found is None:code='INVALID_ARTIFACT'
            else:code,artifact,reward='OK',found.artifact_id,found.value
        elif kind=='ENGAGE':
            if target in schedules:code='PATROL_ENGAGE_FORBIDDEN'
            else:
                found=next((e for e in level.enemies if e.enemy_id==target and target not in defeated
                    and abs(e.position.row-position[0])+abs(e.position.column-position[1])==1),None)
                if found is None:code='INVALID_ENEMY'
                else:code,enemy,penalty='OK',found.enemy_id,found.encounter_penalty
        elif kind=='EXIT':
            completed=position==(level.exit.row,level.exit.column);code='OK' if completed else 'NOT_AT_EXIT'
        else:code='OK'
    accepted=code=='OK';next_turn=turn+int(accepted);next_phase=phase_turn
    if accepted:
        order+=['apply','turn']
        if artifact is not None:collected.add(artifact)
        if enemy is not None:defeated.add(enemy)
        if completed:terminal='EXIT';order.append('exit')
        else:
            next_phase=next_turn;order+=['patrol','collision']
            occupied={(p.positions[(p.initial_phase+next_phase)%len(p.positions)].row,
                       p.positions[(p.initial_phase+next_phase)%len(p.positions)].column) for p in schedules.values()}
            if destination in occupied:terminal='PATROL_COLLISION'
            else:
                order.append('deadline')
                if rules['deadline_turn'] is not None and next_turn>=rules['deadline_turn']:terminal='DEADLINE'
                else:
                    order.append('cap')
                    if next_turn>=cap:terminal='MAX_TURNS'
                    else:order.append('continue')
    expected=dict(attempt=index,accepted=accepted,code=code,action=event['action'],turn_before=turn,turn_after=next_turn,
        position_before=list(position),position_after=list(destination),artifact_reward=reward,encounter_penalty=penalty,
        collected_artifact_id=artifact,defeated_enemy_id=enemy,patrol_turn_before=phase_turn,patrol_turn_after=next_phase,
        order=order,terminal=terminal)
    if encode(event)!=encode(expected):raise ReplayError("EVENT_MISMATCH")
    return destination,next_turn,next_phase,completed,accepted,code,terminal


def validate_history(record,level,policy,baseline,cap,rules):
    events,frames=record['events'],record['frames']
    if type(events) is not list or not 1<=len(events)<=cap or type(frames) is not list or len(frames)!=len(events)+1:raise ReplayError("INVALID_HISTORY")
    position,turn,phase_turn,collected,defeated=(level.start.row,level.start.column),0,0,set(),set()
    snapshots=[snapshot(level,policy,baseline,cap,rules,position,turn,collected,defeated,phase_turn)]
    rebuilt=[frame_record(snapshots[0],0)];stopped,completed,code,terminal=False,False,None,None
    for index,event in enumerate(events,1):
        if stopped:raise ReplayError("EVENT_AFTER_TERMINATION")
        position,turn,phase_turn,completed,accepted,code,terminal=_event(event,index,level,rules,cap,position,turn,phase_turn,collected,defeated)
        stopped=completed or not accepted or terminal is not None
        frame=snapshot(level,policy,baseline,cap,rules,position,turn,collected,defeated,phase_turn)
        snapshots.append(frame);rebuilt.append(frame_record(frame,phase_turn))
    if not stopped:raise ReplayError("TRUNCATED_HISTORY")
    if encode(frames)!=encode(rebuilt):raise ReplayError("FRAME_MISMATCH")
    metrics=event_metrics(events,baseline,policy,completed)
    if metrics['certification_defect']:outcome,final_code='HOST_CERTIFICATION_DEFECT','C_BELOW_L'
    elif completed:outcome,final_code='COMPLETED','EXIT'
    elif code in WORKER_FAILURE_CODES:outcome,final_code='WORKER_ERROR',code
    elif code in ('CONTROLLER_EXCEPTION','CONTROLLER_CONTRACT') or code in SETUP_FAILURE_CODES:outcome,final_code='CONTROLLER_ERROR',code
    elif code!='OK':outcome,final_code='ILLEGAL_ACTION',code
    elif terminal=='PATROL_COLLISION':outcome,final_code='COLLISION',terminal
    elif terminal=='DEADLINE':outcome,final_code='DEADLINE',terminal
    else:outcome,final_code='TURN_LIMIT','MAX_TURNS'
    summary=dict(outcome=outcome,code=final_code,completed=completed,max_turns=cap,deadline_turn=rules['deadline_turn'],**metrics)
    if encode(summary)!=encode(record['summary']):raise ReplayError("SUMMARY_MISMATCH")
    return ReplayView(tuple(snapshots),encode(summary))

