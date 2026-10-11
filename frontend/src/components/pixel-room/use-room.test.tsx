import {renderHook,waitFor,act} from '@testing-library/react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {useRoom} from './use-room';
import {api} from '@/lib/api';
import {fixture} from './test-fixture';
vi.mock('@/lib/api',()=>({api:vi.fn()}));
afterEach(()=>{vi.clearAllMocks();});
describe('read-only room polling',()=>{
  it('uses only protected GET reads and makes no requests for a visual preview',async()=>{const a=fixture();vi.mocked(api).mockImplementation(async(path)=>path.startsWith('workbench')?a.detail:a.replay);const hook=renderHook(()=>useRoom(undefined,0));expect(api).not.toHaveBeenCalled();hook.unmount();const connected=renderHook(()=>useRoom('case-a',0));await waitFor(()=>expect(connected.result.current.snapshot?.detail.case.id).toBe('case-a'));expect(api).toHaveBeenCalledTimes(2);for(const [path,options] of vi.mocked(api).mock.calls){expect(path).toMatch(/^(workbench|reliability)\/cases\/case-a/);expect(options?.method).toBeUndefined();expect(options?.body).toBeUndefined();}connected.unmount();});
  it('refuses mixed case snapshots and aborts requests on case switching or unmount',async()=>{const a=fixture();vi.mocked(api).mockImplementation(async(path)=>path.startsWith('workbench')?a.detail:a.replay);const hook=renderHook(({id})=>useRoom(id,0),{initialProps:{id:'case-a'}});await waitFor(()=>expect(hook.result.current.snapshot).toBeDefined());const oldSignal=vi.mocked(api).mock.calls[0][1]?.signal;act(()=>hook.rerender({id:'case-b'}));expect(hook.result.current.snapshot).toBeUndefined();expect(oldSignal?.aborted).toBe(true);await waitFor(()=>expect(hook.result.current.error).toContain('Case identity mismatch'));hook.unmount();expect(vi.mocked(api).mock.calls.at(-1)?.[1]?.signal?.aborted).toBe(true);});
});
