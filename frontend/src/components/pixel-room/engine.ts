import { findPath, TileType } from './vendor/pathfinding';
export const WIDTH = 576, HEIGHT = 416, TILE = 16;
export const roles = [
  {id: 'TRANSACTION', name: 'Transaction Agent', responsibility: 'Payment & ledger investigation', color: '#54ceb0', col: 7, row: 9, sprite: 0},
  {id: 'TECHNOLOGY', name: 'Technology Agent', responsibility: 'API & dependency investigation', color: '#69bafa', col: 18, row: 9, sprite: 1},
  {id: 'RISK', name: 'Risk Agent', responsibility: 'Risk & policy investigation', color: '#e4b16a', col: 29, row: 9, sprite: 2},
  {id: 'SUPERVISOR', name: 'Supervisor Agent', responsibility: 'Cross-checking recorded findings', color: '#b1a0f0', col: 18, row: 16, sprite: 3},
  {id: 'HUMAN', name: 'Human Reviewer', responsibility: 'Authorized employee oversight', color: '#f0bd71', col: 7, row: 23, sprite: 4},
  {id: 'EXECUTION', name: 'Execution Operator', responsibility: 'Deterministic synthetic service', color: '#79bcf1', col: 18, row: 23, sprite: 5},
  {id: 'VERIFICATION', name: 'Verification Operator', responsibility: 'Independent observed verification', color: '#91d5a3', col: 29, row: 23, sprite: 0},
] as const;
export type Role = typeof roles[number]['id'];
export type VisualState = 'IDLE' | 'TASK_RECEIVED' | 'WORKING' | 'READING' | 'STANDING_UP' | 'WALKING_TO_RECIPIENT' | 'HANDOFF' | 'RETURNING_TO_DESK' | 'SITTING' | 'WAITING' | 'BLOCKED' | 'ERROR' | 'REINVESTIGATING' | 'VERIFIED';
export interface VisualEvent {id: string; role: Role; state: VisualState; recipient?: Role; label: string; at?: string; record?: Record<string, unknown>}
export interface Point {col: number; row: number}
export interface Actor {role: Role; col: number; row: number; x: number; y: number; dir: number; state: VisualState; time: number; path: Point[]; status: string}
export function createMap() {
  const map: number[][] = Array.from({length: 26}, (_, r) => Array.from({length: 36}, (_, c) => r < 5 || r === 25 || c === 0 || c === 35 ? TileType.WALL : TileType.FLOOR));
  const blocked = new Set<string>();
  for (const role of roles) for (let r = role.row - 3; r < role.row; r++) for (let c = role.col - 2; c <= role.col + 2; c++) blocked.add(`${c},${r}`);
  // Decorative cabinets and plants occupy the perimeter, outside the corridors.
  for (const c of [1, 2, 33, 34]) for (let r = 5; r < 25; r++) blocked.add(`${c},${r}`);
  return {map, blocked};
}
export function route(from: Point, to: Point) {const {map, blocked} = createMap(); for (const r of roles) if (r.col !== from.col || r.row !== from.row) blocked.add(`${r.col},${r.row}`); blocked.delete(`${to.col},${to.row}`); return findPath(from.col, from.row, to.col, to.row, map, blocked);}
export class OfficeEngine {
  actors: Actor[] = roles.map(r => ({role: r.id, col: r.col, row: r.row, x: r.col * TILE + 8, y: r.row * TILE + 8, dir: 3, state: 'IDLE', time: 0, path: [], status: 'No recorded activity'}));
  selected: Role = 'TRANSACTION'; paused = false; reducedMotion = false; elapsed = 0;
  queue: VisualEvent[] = []; seen = new Set<string>(); current?: VisualEvent; phase = ''; phaseTime = 0; completed = 0; received = 0;
  images: HTMLImageElement[] = []; ready = false; loadError = false;
  onChange?: () => void;
  subscribe(callback?: () => void) {this.onChange=callback;}
  pause(value: boolean) {this.paused=value;}
  select(role: Role) {this.selected = role;}
  motion(reduced: boolean) {this.reducedMotion = reduced;}
  async load() {try {this.images = await Promise.all(Array.from({length: 6}, (_, i) => new Promise<HTMLImageElement>((resolve, reject) => {const img = new Image(); img.onload = () => resolve(img); img.onerror = reject; img.src = `/pixel-room/characters/char_${i}.png`;}))); this.ready = true;} catch {this.loadError = true;} this.onChange?.();}
  enqueue(events: VisualEvent[]) {for (const e of events) if (!this.seen.has(e.id)) {this.seen.add(e.id); this.queue.push(e); this.received++;} if (this.seen.size > 2000) this.seen = new Set([...this.seen].slice(-1000)); if (this.queue.length > 500) {this.fastForward();} }
  reset() {this.queue = []; this.seen.clear(); this.current = undefined; this.phase = ''; this.completed = 0; this.received = 0; for (const a of this.actors) {const r = roles.find(r => r.id === a.role)!; Object.assign(a, {col: r.col, row: r.row, x: r.col * TILE + 8, y: r.row * TILE + 8, state: 'IDLE', path: [], time: 0, status: 'No recorded activity'});} this.onChange?.();}
  actor(id: Role) {return this.actors.find(a => a.role === id)!;}
  setStatus(role: Role, state: VisualState, status: string) {const a = this.actor(role); a.state = state; a.status = status; a.time = 0;}
  fastForward() {const all = [...(this.current ? [this.current] : []), ...this.queue]; for (const e of all) {this.setStatus(e.role, e.recipient ? 'WAITING' : e.state, e.label); if (e.recipient) this.setStatus(e.recipient, 'WAITING', 'Recorded handoff available');} this.completed += all.length; this.current = undefined; this.queue = []; this.phase = ''; for (const a of this.actors) {const r = roles.find(r => r.id === a.role)!; a.path = []; a.x = r.col * TILE + 8; a.y = r.row * TILE + 8; a.col = r.col; a.row = r.row;} this.onChange?.();}
  update(dt: number) {
    this.elapsed += dt;
    if (this.paused) return;
    if (!this.current && this.queue.length) {this.current = this.queue.shift()!; this.phaseTime = 0; const e = this.current; this.phase = e.recipient ? 'stand' : 'activity'; this.setStatus(e.role, e.recipient ? 'STANDING_UP' : e.state, e.label); this.onChange?.();}
    for (const a of this.actors) {a.time += dt; if (!a.path.length) continue; const p = a.path[0], tx = p.col * TILE + 8, ty = p.row * TILE + 8, dx = tx - a.x, dy = ty - a.y; a.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 2 : 1) : (dy > 0 ? 0 : 3); const length = Math.hypot(dx, dy), step = (this.reducedMotion ? 180 : 48) * dt; if (length <= step) {a.x = tx; a.y = ty; a.col = p.col; a.row = p.row; a.path.shift();} else {a.x += dx / length * step; a.y += dy / length * step;} }
    if (!this.current) return;
    this.phaseTime += dt;
    const e = this.current, a = this.actor(e.role);
    const next = (phase: string) => {this.phase = phase; this.phaseTime = 0; this.onChange?.();};
    const finish = () => {this.current = undefined; this.completed++; this.phase = ''; this.onChange?.();};
    if (this.phase === 'activity' && this.phaseTime > .85) finish();
    else if (this.phase === 'stand' && this.phaseTime > .6) {const recipient = roles.find(r => r.id === e.recipient)!; a.path = route(a, {col: recipient.col - 3, row: recipient.row}); a.state = 'WALKING_TO_RECIPIENT'; if (!a.path.length) {a.state = 'ERROR'; a.status = 'Visual route unavailable'; finish();} else next('walk');}
    else if (this.phase === 'walk' && !a.path.length) {a.state = 'HANDOFF'; a.dir = 2; this.actor(e.recipient!).dir = 1; next('handoff');}
    else if (this.phase === 'handoff' && this.phaseTime > 1.35) {this.setStatus(e.recipient!, 'TASK_RECEIVED', 'Acknowledging recorded handoff'); const home = roles.find(r => r.id === e.role)!; a.path = route(a, home); a.state = 'RETURNING_TO_DESK'; next('return');}
    else if (this.phase === 'return' && !a.path.length) {a.state = 'SITTING'; a.dir = 3; next('sit');}
    else if (this.phase === 'sit' && this.phaseTime > .5) {a.state = 'WAITING'; a.status = 'Handoff displayed · waiting for recorded work'; this.actor(e.recipient!).dir = 3; finish();}
  }
  hit(x: number, y: number): Role | undefined {return [...this.actors].reverse().find(a => Math.abs(x - a.x) < 18 && y > a.y - 35 && y < a.y + 15)?.role;}
  draw(ctx: CanvasRenderingContext2D) {
    ctx.imageSmoothingEnabled = false;
    const rect = (x: number, y: number, w: number, h: number, color: string) => {ctx.fillStyle = color; ctx.fillRect(Math.round(x), Math.round(y), w, h);};
    const word = (s: string, x: number, y: number, color = '#b8ccd5', size = 7) => {ctx.fillStyle = color; ctx.font = `${size}px monospace`; ctx.fillText(s, x, y);};
    rect(0, 0, WIDTH, HEIGHT, '#121e29');
    // Slate wall, brick seams, oak parquet floor, inset skirting.
    for (let y = 0; y < 80; y += 16) for (let x = 0; x < WIDTH; x += 32) {rect(x + (y % 32 ? 16 : 0), y, 31, 15, y < 32 ? '#243443' : '#2c3e4c'); rect(x, y + 14, 32, 1, '#172530');}
    for (let r = 5; r < 26; r++) for (let c = 0; c < 36; c++) {const x = c * 16, y = r * 16; rect(x, y, 16, 16, (c + Math.floor(r / 2)) % 3 === 0 ? '#696359' : '#625e56'); rect(x, y + 15, 16, 1, '#504f49'); rect(x + (r % 2 ? 8 : 0), y, 1, 15, '#57554c'); if ((c * 7 + r) % 4 === 0) rect(x + 3, y + 6, 8, 1, '#716a5e');}
    rect(0, 76, WIDTH, 4, '#111f29'); rect(0, 80, 16, 336, '#253640'); rect(560, 80, 16, 336, '#253640'); rect(16, 408, 544, 8, '#26343b');
    // Wall sign and two information boards.
    rect(22, 18, 176, 45, '#101a25'); rect(24, 20, 172, 41, '#1b2c3a'); word('✦ ResolveOS', 40, 39, '#a3d5f7', 16); word('OPERATIONS / SYNTHETIC', 40, 53, '#80a6bf', 7);
    rect(214, 18, 175, 45, '#142634'); word('EVIDENCE → REVIEW → VERIFY', 226, 34, '#8fb4c7', 8); for (let i = 0; i < 5; i++) {rect(229 + i * 31, 44, 21, 2, '#385567'); rect(231 + i * 31, 49, 15, 2, '#497b87');}
    rect(406, 18, 145, 45, '#18232c'); word('NO LIVE BANKING', 419, 35, '#d8be91', 10); word('Human-supervised operations', 418, 52, '#8ca2ad', 7);
    // Original plants, file cabinets, wall shelves and meeting lounge.
    const plant = (x: number, y: number) => {rect(x-5,y,10,9,'#896c53');rect(x-4,y+8,8,2,'#463d35');rect(x-1,y-16,2,17,'#658769');for(const [dx,dy] of [[-7,-13],[3,-20],[-6,-24],[2,-10]]) {rect(x+dx,y+dy,6,7,'#3c7258');rect(x+dx+1,y+dy,4,3,'#589574');}};
    for (const y of [112, 212, 326]) {plant(27, y); plant(548, y);}
    const cabinet=(x:number,y:number)=>{rect(x,y,20,38,'#344551');rect(x+2,y+2,16,34,'#46535a');for(let i=0;i<3;i++){rect(x+3,y+4+i*10,14,8,'#637074');rect(x+8,y+7+i*10,5,1,'#252f34');}};
    cabinet(18,145);cabinet(538,145);cabinet(18,353);cabinet(538,353);
    for(const x of [22,422]) {rect(x,66,125,5,'#88694d'); for(let i=0;i<14;i++) rect(x+3+i*8,56+(i%3),5,10-(i%3),['#996d54','#426981','#798373'][i%3]);}
    // Carpet and shared handoff space, with quiet boundary stitching.
    rect(207,225,162,59,'#364f58');rect(210,228,156,53,'#405c63'); word('REVIEW & HANDOFF', 240, 274, '#99b2b6', 7);
    rect(44,242,86,35,'#424f58');rect(46,244,82,27,'#6d797c');rect(45,264,84,9,'#53656d');for(let x=48;x<126;x+=25)rect(x,247,22,14,'#7c8686');
    rect(440,242,77,35,'#424f58');rect(442,244,73,27,'#6d797c');rect(441,264,75,9,'#53656d');
    // Y-sorted desk + character drawing. Furniture bases match collision footprints.
    const items: {y:number;draw:()=>void}[]=[];
    for(const r of roles) {const x=r.col*TILE+8,y=r.row*TILE+8;
      items.push({y:y-9,draw:()=>{rect(x-36,y-37,76,29,'#29323a');rect(x-35,y-39,70,23,'#9b7c58');rect(x-32,y-37,64,19,'#b18b63');rect(x-32,y-18,4,13,'#665340');rect(x+28,y-18,4,13,'#665340');rect(x-12,y-55,25,17,'#151f27');rect(x-10,y-53,21,12,'#346278');rect(x-8,y-51,8,1,r.color);for(let i=0;i<3;i++)rect(x-8,y-48+i*2,10+(i%2)*5,1,'#80b0c1');rect(x-2,y-38,4,3,'#1b2c35');rect(x-9,y-31,21,5,'#47545b');for(let i=0;i<7;i++)rect(x-7+i*2,y-30,1,1,'#98a7a7');rect(x+20,y-33,7,8,'#ddd9bb');rect(x+26,y-31,2,4,'#c6b88e');rect(x-29,y-31,9,11,'#d3d3b9');rect(x-27,y-29,5,1,'#888d84');rect(x-16,y-13,32,16,'#303e49');rect(x-13,y-11,26,12,'#586877');plant(x+30,y-47);}});
    }
    for(const a of this.actors) items.push({y:a.y,draw:()=>{
      const r=roles.find(r=>r.id===a.role)!; const seated=['IDLE','WORKING','READING','WAITING','BLOCKED','ERROR','VERIFIED','REINVESTIGATING'].includes(a.state);
      const walking=!!a.path.length; const reading=['READING','HANDOFF'].includes(a.state); const animated=['WORKING','READING','REINVESTIGATING'].includes(a.state);
      const f=walking?[0,1,2,1][Math.floor(a.time/.12)%4]:animated?(reading?5:3)+Math.floor(a.time/.27)%2:1;
      const dir=seated?3:a.dir; const row=dir===3?1:dir===0?0:2; const bob=this.reducedMotion?0:Math.sin(this.elapsed*2+a.col)*.35;
      if(this.selected===a.role){rect(a.x-13,a.y+1,26,2,r.color);rect(a.x-16,a.y-32,2,11,r.color);rect(a.x+14,a.y-32,2,11,r.color);}
      rect(a.x-7,a.y+1,14,3,'#393c36');
      const img=this.images[r.sprite]; if(img) {ctx.save();if(a.role==='VERIFICATION')ctx.filter='hue-rotate(80deg)';ctx.translate(Math.round(a.x),Math.round(a.y+(seated?3:bob)));if(dir===1)ctx.scale(-1,1);ctx.drawImage(img,f*16,row*32,16,32,-8,-30,16,32);ctx.restore();}
      if(a.state==='STANDING_UP'||a.state==='SITTING') rect(a.x-7,a.y-2,14,2,r.color);
      if(['WALKING_TO_RECIPIENT','HANDOFF'].includes(a.state)){const t=this.phase==='handoff'?Math.min(this.phaseTime/1.1,1):0;rect(a.x+6+t*14,a.y-15,7,9,'#ede5c8');rect(a.x+7+t*14,a.y-13,4,1,'#7d8b89');}
      const alert=['BLOCKED','ERROR','TASK_RECEIVED','VERIFIED','REINVESTIGATING'].includes(a.state); if(alert){rect(a.x-8,a.y-43,16,10,a.state==='VERIFIED'?'#245b48':a.state==='BLOCKED'||a.state==='ERROR'?'#783e3b':'#334a61');word(a.state==='VERIFIED'?'OK':a.state==='BLOCKED'||a.state==='ERROR'?'!':'...',a.x-5,a.y-36,'#edf4ee',7);}
      const name=r.name.replace(' Agent','').replace(' Operator','');ctx.font='7px monospace';const w=ctx.measureText(name).width+14;rect(a.x-w/2,a.y+6,w,13,'#15232ded');rect(a.x-w/2+4,a.y+11,3,3,r.color);word(name,a.x-w/2+10,a.y+15,'#d1d9de',7);
    }});
    items.sort((a,b)=>a.y-b.y).forEach(i=>i.draw());
    // Quiet ambient server LED animation, unrelated to operational state.
    rect(484,291,40,42,'#1f303b');for(let i=0;i<5;i++){rect(487,295+i*7,34,5,'#3a4c58');rect(491,297+i*7,12,1,'#78919b');rect(515,297+i*7,2,2,Math.floor(this.elapsed)%2?'#7cb0b5':'#496e77');}
    if(!this.ready){rect(165,180,245,40,'#15232e');word(this.loadError?'Character assets unavailable':'Loading character sprites…',181,203,'#d4dde5',11);}
  }
}
