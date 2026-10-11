import {record,rows,text,words,type CaseDetail,type Json,type Replay} from '@/lib/types';
import {roles,type Role,type VisualEvent,type VisualState} from './engine';
export interface Snapshot {detail:CaseDetail; replay:Replay; receivedAt:string}
export const MAX_EVENTS=300;
export function taskRole(task:Json):Role|undefined {const type=text(task.task_type,'');return type.startsWith('INVESTIGATE_')?roleOf(type.slice(12)):type==='REQUEST_SUPERVISOR_REVIEW'?'SUPERVISOR':type==='REQUEST_HUMAN_REVIEW'?'HUMAN':type==='PREPARE_EXECUTION'?'EXECUTION':type==='REQUEST_VERIFICATION'?'VERIFICATION':undefined;}
function roleOf(role:unknown):Role|undefined {return roles.find(r=>r.id===role)?.id;}
export function eventKey(caseId:string,event:Json) {return `${caseId}:${text(event.kind)}:${text(event.id)}:${text(event.at)}`;}
export function orderedTimeline(replay:Replay):Json[] {return [...new Map(replay.timeline.map(e=>[eventKey(replay.case_id,e),e])).values()].filter(e=>!Number.isNaN(Date.parse(text(e.at,'')))).sort((a,b)=>text(a.at).localeCompare(text(b.at))||text(a.kind).localeCompare(text(b.kind))||text(a.id).localeCompare(text(b.id))).slice(-MAX_EVENTS);}
export function roomTimeline(snapshot:Snapshot):Json[] {
  const taskEvents=rows(snapshot.detail.tasks.events).flatMap(event=>{const task=rows(snapshot.detail.tasks.tasks).find(t=>t.id===event.task_id);const role=task&&taskRole(task);return role?[{id:event.id,kind:`TASK_${text(event.event_type)}`,at:event.created_at,payload:{role,task_id:event.task_id,recorded_details:event.details},basis:'RECORDED_TASK_HISTORY'}]:[];});
  return orderedTimeline({...snapshot.replay,timeline:[...snapshot.replay.timeline,...taskEvents]});
}
export function visualEvents(snapshot:Snapshot):VisualEvent[] {
  const {detail}=snapshot;
  const timeline=roomTimeline(snapshot);
  const result:VisualEvent[]=[];
  for(const event of timeline){const p=record(event.payload),kind=text(event.kind);let role=roleOf(p.role),state:VisualState|undefined,recipient:Role|undefined;
    if(kind==='TASK_task_created'||kind==='TASK_task_requeued'){state='TASK_RECEIVED';}
    if(kind==='TASK_task_claimed'){state=role==='SUPERVISOR'?'READING':'WORKING';}
    if(kind==='TASK_task_failed'){state='ERROR';}
    if(kind==='TASK_task_cancelled'||kind==='TASK_task_retry_scheduled'){state='WAITING';}
    if(kind==='INVESTIGATION_STARTED'&&role)state='WORKING';
    if(kind==='INVESTIGATION_COMPLETED'&&role){state=p.status==='COMPLETED'?'HANDOFF':p.status==='FAILED'?'ERROR':'WAITING';if(p.status==='COMPLETED')recipient='SUPERVISOR';}
    if(kind==='SUPERVISOR_REVIEW'){role='SUPERVISOR';state=p.outcome==='ESCALATE'?'HANDOFF':p.outcome==='REINVESTIGATE'?'REINVESTIGATING':'READING';if(p.outcome==='ESCALATE')recipient='HUMAN';}
    if(kind==='DETERMINISTIC_CONTROL'){role='SUPERVISOR';state=p.outcome==='BLOCKED'?'BLOCKED':p.outcome==='HUMAN_APPROVAL_REQUIRED'?'HANDOFF':'READING';if(p.outcome==='HUMAN_APPROVAL_REQUIRED')recipient='HUMAN';}
    if(kind.startsWith('WORKFLOW_REVIEW_')||kind.startsWith('ACTION_APPROVAL_')){role='HUMAN';state=kind.endsWith('REJECT')?'BLOCKED':kind.endsWith('APPROVE')?'TASK_RECEIVED':'WAITING';}
    if(kind==='synthetic_execution_scheduled'){role='EXECUTION';state='TASK_RECEIVED';}
    if(kind==='synthetic_confirmation_replayed'){role='EXECUTION';state='HANDOFF';recipient='VERIFICATION';}
    if(kind==='synthetic_execution_terminal_failure'){role='EXECUTION';state='ERROR';}
    if(kind==='INDEPENDENT_VERIFICATION'){role='VERIFICATION';state=p.success===true&&p.verification_type==='INDEPENDENT_SYNTHETIC_CONFIRMATION'?'VERIFIED':'BLOCKED';}
    if(kind==='SUPERVISOR_REVIEW'&&p.outcome==='REINVESTIGATE'){const review=detail.supervisor_reviews.find(r=>r.id===event.id);for(const target of words(record(review?.result).targeted_specialists)){const targetRole=roleOf(target);if(targetRole)result.push({id:eventKey(detail.case.id,event)+':'+targetRole,role:targetRole,state:'TASK_RECEIVED',label:'Recorded targeted reinvestigation request',at:text(event.at),record:review});}}
    if(role&&state)result.push({id:eventKey(detail.case.id,event),role,state,recipient,label:`${kind} · ${text(p.summary,text(p.outcome,text(p.status,'Recorded event')))}`,at:text(event.at),record:event});
  }
  return result;
}
export function currentAgent(snapshot:Snapshot,role:Role) {
  const {detail}=snapshot;
  const tasks=rows(detail.tasks.tasks).filter(t=>taskRole(t)===role);
  const task=tasks[0];const run=detail.investigations.find(r=>r.role===role);
  const review=role==='SUPERVISOR'?detail.supervisor_reviews[0]:undefined;
  const result=record(run?.result??review?.result);
  const taskStatus=text(task?.status,'');
  const status=run&&run.status==='RUNNING'?'RUNNING':taskStatus==='RUNNING'?'RUNNING':taskStatus||text(run?.status,review?'RECORDED_REVIEW':'NO_RECORDED_TASK');
  let state:VisualState=status==='RUNNING'?(role==='SUPERVISOR'?'READING':'WORKING'):['DEAD_LETTER','FAILED'].includes(status)?'ERROR':status==='COMPLETED'?'WAITING':task?'WAITING':'IDLE';
  if(role==='SUPERVISOR'&&detail.authorizations[0]?.outcome==='BLOCKED')state='BLOCKED';
  if(role==='HUMAN'&&detail.case.status==='AWAITING_HUMAN')state='WAITING';
  if(role==='VERIFICATION') {const v=[...orderedTimeline(snapshot.replay)].reverse().find(e=>e.kind==='INDEPENDENT_VERIFICATION');if(v&&record(v.payload).success===true&&record(v.payload).verification_type==='INDEPENDENT_SYNTHETIC_CONFIRMATION'&&detail.case.status==='RESOLVED')state='VERIFIED';else if(v&&record(v.payload).success===false)state='BLOCKED';}
  const evidenceIds=new Set([...rows(result.findings).flatMap(f=>words(f.evidence_ids)),...rows(result.supported_conclusions).flatMap(f=>words(f.evidence_ids)),...words(result.evidence_ids)]);
  const evidence=detail.evidence.filter(e=>evidenceIds.has(text(e.id)));
  const events=visualEvents(snapshot).filter(e=>e.role===role||e.recipient===role);
  return {task,run,review,result,status,state,evidence,events,next:words(result.suggested_next_steps)[0]??words(result.required_additional_checks)[0]??'No next step is established in the recorded result.'};
}
export interface Stage {id:string;name:string;status:string;records:Json[]}
export function stages(snapshot:Snapshot):Stage[] {
  const timeline=orderedTimeline(snapshot.replay),{detail}=snapshot;
  const stage=(id:string,name:string,kinds:string[]):Stage=>{const records=timeline.filter(e=>kinds.includes(text(e.kind)));return {id,name,status:records.length?'Recorded':'Not started',records};};
  const items=[stage('detected','Detected',['DETECTED','CLASSIFIED']),stage('investigation','Investigation',['INVESTIGATION_STARTED','INVESTIGATION_COMPLETED']),stage('decision','Decision & controls',['SUPERVISOR_REVIEW','DETERMINISTIC_CONTROL']),stage('human','Human approval',timeline.filter(e=>text(e.kind).startsWith('WORKFLOW_REVIEW_')||text(e.kind).startsWith('ACTION_APPROVAL_')).map(e=>text(e.kind))),stage('execution','Execution',['synthetic_execution_scheduled','synthetic_confirmation_replayed','synthetic_execution_terminal_failure']),stage('verification','Verification',['INDEPENDENT_VERIFICATION'])];
  for(const s of items){if(s.id==='investigation'){if(rows(detail.tasks.tasks).some(t=>taskRole(t)&&['TRANSACTION','TECHNOLOGY','RISK'].includes(taskRole(t)!)&&t.status==='RUNNING'))s.status='Active';else if(s.records.some(e=>e.kind==='INVESTIGATION_COMPLETED'))s.status='Completed records';}
    if(s.id==='decision'&&detail.authorizations[0]?.outcome==='BLOCKED')s.status='Blocked';
    if(s.id==='human'){if(detail.case.status==='AWAITING_HUMAN'||detail.authorizations[0]?.approval?.status==='OPEN')s.status='Waiting for human';else if(!s.records.length)s.status='Conditional';}
    if(s.id==='execution'){if(s.records.some(e=>e.kind==='synthetic_confirmation_replayed'))s.status='Effect recorded';if(s.records.at(-1)?.kind==='synthetic_execution_terminal_failure')s.status='Failed';if(rows(detail.tasks.tasks).some(t=>taskRole(t)==='EXECUTION'&&t.status==='RUNNING'))s.status='Active';}
    if(s.id==='verification'){const p=record(s.records.at(-1)?.payload);s.status=p.success===true&&p.verification_type==='INDEPENDENT_SYNTHETIC_CONFIRMATION'&&detail.case.status==='RESOLVED'?'Verified resolution':p.success===false?'Blocked':rows(detail.tasks.tasks).some(t=>taskRole(t)==='VERIFICATION'&&t.status==='RUNNING')?'Active':s.status;}}
  return items;
}
