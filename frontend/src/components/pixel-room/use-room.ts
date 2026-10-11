"use client";
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import type {CaseDetail,Replay} from '@/lib/types';
import type {Snapshot} from './adapter';
export function useRoom(caseId:string|undefined,revision:number) {
  const [state,setState]=useState<{caseId?:string;snapshot?:Snapshot;error?:string}>({});
  useEffect(()=>{if(!caseId)return;let active=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
    async function poll(){const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(10000)]);try{const [detail,replay]=await Promise.all([api<CaseDetail>(`workbench/cases/${caseId}`,{signal}),api<Replay>(`reliability/cases/${caseId}/replay`,{signal})]);if(detail.case.id!==caseId||replay.case_id!==caseId)throw new Error('Case identity mismatch; snapshot refused');if(active)setState({caseId,snapshot:{detail,replay,receivedAt:new Date().toISOString()}});}catch(e){if(active)setState(old=>({caseId,snapshot:old.caseId===caseId?old.snapshot:undefined,error:e instanceof Error?e.message:'Connection unavailable'}));}finally{if(active)timer=setTimeout(poll,3000);}}
    void poll();return()=>{active=false;controller.abort();clearTimeout(timer);};
  },[caseId,revision]);
  return state.caseId===caseId?state:{};
}
