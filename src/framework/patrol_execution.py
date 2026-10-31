"""Shared patrol execution; wrappers own admission and wire trust."""
from src.api import Position, WorldAction, WorldActionType
from src.framework.patrol_records import allowed_actions, frame_record, snapshot
from src.framework.patrol_values import PatrolRun, event_metrics
from src.framework.generated_static.values import CallbackFailure, WORKER_FAILURE_CODES, SETUP_FAILURE_CODES

MOVES = {WorldActionType.MOVE_NORTH:(-1,0),WorldActionType.MOVE_SOUTH:(1,0),
         WorldActionType.MOVE_WEST:(0,-1),WorldActionType.MOVE_EAST:(0,1)}


def _action(value):
    try:
        if (type(value) is not WorldAction or type(value.action_type) is not WorldActionType
                or not any(value.action_type is k for k in WorldActionType)
                or (value.target_id is not None and type(value.target_id) is not str)):
            return None
        return WorldAction(value.action_type,target_id=value.target_id)
    except (AttributeError,ValueError,TypeError):
        return None


def _apply(level,action,position,collected,defeated,phase_turn,rules):
    kind,target=action.action_type,action.target_id
    destination,reward,penalty,artifact,enemy,completed=position,0,0,None,None,False
    patrols={p.enemy_id:p for p in level.patrols}
    occupied={(e.position.row,e.position.column) for e in level.enemies
              if e.enemy_id not in patrols and e.enemy_id not in defeated}
    for p in patrols.values():
        pos=p.positions[(p.initial_phase+phase_turn)%p.period]
        occupied.add((pos.row,pos.column))
    code="OK"
    if kind not in allowed_actions(rules): code="ACTION_DISABLED"
    elif kind not in (WorldActionType.COLLECT,WorldActionType.ENGAGE) and target is not None: code="UNEXPECTED_TARGET"
    elif kind in MOVES:
        dr,dc=MOVES[kind];proposed=(position[0]+dr,position[1]+dc)
        if not level.terrain.is_traversable(Position(*proposed)): code="BLOCKED_TERRAIN"
        elif proposed in occupied: code="BLOCKED_ENEMY"
        else: destination=proposed
    elif kind is WorldActionType.COLLECT:
        found=next((a for a in level.artifacts if a.artifact_id==target),None)
        if found is None or target in collected or (found.position.row,found.position.column)!=position: code="INVALID_ARTIFACT"
        else: reward,artifact=found.value,found.artifact_id
    elif kind is WorldActionType.ENGAGE:
        found=next((e for e in level.enemies if e.enemy_id==target),None)
        if target in patrols: code="PATROL_ENGAGE_FORBIDDEN"
        elif found is None or target in defeated or abs(found.position.row-position[0])+abs(found.position.column-position[1])!=1: code="INVALID_ENEMY"
        else: penalty,enemy=found.encounter_penalty,found.enemy_id
    elif kind is WorldActionType.EXIT:
        if position!=(level.exit.row,level.exit.column):code="NOT_AT_EXIT"
        else:completed=True
    return code,destination,reward,penalty,artifact,enemy,completed


def _after_nonexit(level,position,turn,rules,cap):
    order=["patrol","collision"]
    if any((p.positions[(p.initial_phase+turn)%p.period].row,p.positions[(p.initial_phase+turn)%p.period].column)==position
           for p in level.patrols): return "PATROL_COLLISION",order
    order.append("deadline")
    if rules["deadline_turn"] is not None and turn>=rules["deadline_turn"]: return "DEADLINE",order
    order.append("cap")
    if turn>=cap:return "MAX_TURNS",order
    order.append("continue")
    return None,order


def run_history(level,cap,rules,baseline,policy,admission,controller,build_record,
                snapshot_factory=snapshot,action_owner=_action,apply_action=_apply,after_nonexit=_after_nonexit):
    position,turn,phase_turn,collected,defeated=(level.start.row,level.start.column),0,0,set(),set()
    events,frames=[],[]
    def frame():return snapshot_factory(level,policy,baseline,cap,rules,position,turn,collected,defeated,phase_turn)
    frames.append(frame_record(frame(),phase_turn))
    try:
        callback=getattr(controller,"choose_action")
        entry_error=None if callable(callback) else "CONTROLLER_CONTRACT"
    except AttributeError: callback,entry_error=None,"CONTROLLER_CONTRACT"
    except Exception: callback,entry_error=None,"CONTROLLER_EXCEPTION"
    completed,terminal,code=False,None,None
    while turn<cap:
        action=None;order=["observe","callback"]
        if entry_error is not None:code=entry_error
        else:
            public_frame,agent_id=frame(),level.character.agent_id
            try: returned=callback(public_frame,agent_id)
            except CallbackFailure as failure:code=failure.code
            except Exception:code="CONTROLLER_EXCEPTION"
            else:
                order.append("validate");action=action_owner(returned);code="MALFORMED_ACTION" if action is None else "OK"
        destination,reward,penalty,artifact,enemy=position,0,0,None,None
        if action is not None:
            code,destination,reward,penalty,artifact,enemy,completed=apply_action(level,action,position,collected,defeated,phase_turn,rules)
        accepted=code=="OK"
        event=dict(attempt=len(events)+1,accepted=accepted,code=code,
            action=None if action is None else dict(action_type=action.action_type.value,target_id=action.target_id),
            turn_before=turn,turn_after=turn+int(accepted),position_before=list(position),position_after=list(destination),
            artifact_reward=reward,encounter_penalty=penalty,collected_artifact_id=artifact,defeated_enemy_id=enemy,
            patrol_turn_before=phase_turn)
        if accepted:
            position,turn=destination,turn+1
            if artifact is not None:collected.add(artifact)
            if enemy is not None:defeated.add(enemy)
            order+=['apply','turn']
            if completed:terminal="EXIT";order.append("exit")
            else:
                phase_turn=turn;terminal,tail=after_nonexit(level,position,turn,rules,cap);order+=tail
        event.update(patrol_turn_after=phase_turn,order=order,terminal=terminal)
        events.append(event);frames.append(frame_record(frame(),phase_turn))
        if completed or not accepted or terminal is not None:break
    metrics=event_metrics(events,baseline,policy,completed)
    if metrics['certification_defect']:outcome,final_code="HOST_CERTIFICATION_DEFECT","C_BELOW_L"
    elif completed:outcome,final_code="COMPLETED","EXIT"
    elif code in WORKER_FAILURE_CODES:outcome,final_code="WORKER_ERROR",code
    elif code in ("CONTROLLER_EXCEPTION","CONTROLLER_CONTRACT") or code in SETUP_FAILURE_CODES:outcome,final_code="CONTROLLER_ERROR",code
    elif code!="OK":outcome,final_code="ILLEGAL_ACTION",code
    elif terminal=="PATROL_COLLISION":outcome,final_code="COLLISION",terminal
    elif terminal=="DEADLINE":outcome,final_code="DEADLINE",terminal
    else:outcome,final_code="TURN_LIMIT","MAX_TURNS"
    summary=dict(outcome=outcome,code=final_code,completed=completed,max_turns=cap,deadline_turn=rules['deadline_turn'],**metrics)
    raw,receipt=build_record(admission,events,frames,summary)
    return PatrolRun(outcome,final_code,raw,receipt)
