"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Activity, ArrowUpRight, BookOpen, Boxes, CheckCheck, ChevronDown, CircleUserRound, FlaskConical, LayoutDashboard, LogOut, PanelLeft, RefreshCw, Search, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { post } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { label, type CasePage, type Identity } from "@/lib/types";
import { Button, Card } from "./ui";
import { Failure, Loading, DataState } from "./data-display";
import { Overview, Cases, IntelligenceView } from "./analytics";
import { CaseView, Investigations, Timeline, Shadow } from "./case-views";
import { Approvals, Memories, ModelLab } from "./governance";

export interface ScreenProps { identity: Identity; revision: number; refresh: () => void; mutate: (path: string, body?: unknown) => Promise<boolean>; busy: boolean }
const navigation = [
  {id: "overview", label: "Overview", icon: LayoutDashboard}, {id: "cases", label: "Cases", icon: Boxes},
  {id: "investigations", label: "Investigations", icon: Search}, {id: "approvals", label: "Approvals", icon: ShieldCheck},
  {id: "timeline", label: "Decision timeline", icon: Workflow}, {id: "intelligence", label: "Intelligence", icon: Sparkles},
  {id: "shadow", label: "Shadow & replay", icon: Activity}, {id: "memory", label: "Reviewed memory", icon: BookOpen},
  {id: "models", label: "Model Lab", icon: FlaskConical},
];
export function Workbench({view, caseId, query}: {view: string; caseId: string; query: string}) {
  const router = useRouter();
  const [identity, setIdentity] = useState<Identity | null>();
  const [sessionError, setSessionError] = useState<Error>();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [selectedCase, setSelectedCase] = useState("");
  const [notice, setNotice] = useState<{error: boolean; message: string}>();
  const [search, setSearch] = useState(query);
  const [mobileNav, setMobileNav] = useState(false);
  useEffect(() => { fetch("/api/session", {cache: "no-store"}).then(async response => {
    if (response.ok) { setIdentity(await response.json()); return; }
    setIdentity(null); if (response.status !== 401) { const body = await response.json(); setSessionError(new Error(body.detail ?? "Connection unavailable")); }
  }).catch(() => { setIdentity(null); setSessionError(new Error("Unable to reach the workbench server")); }); }, []);
  const cases = useData<CasePage>(identity ? "workbench/cases?limit=50" : null, revision);
  const activeCase = selectedCase || caseId || cases.data?.items[0]?.id || "";
  const refresh = () => setRevision(value => value + 1);
  async function mutate(path: string, body?: unknown) {
    setBusy(true); setNotice(undefined);
    try { await post(path, body); setNotice({error: false, message: "Backend request recorded. Refreshing the authoritative state."}); refresh(); return true; }
    catch (error) { setNotice({error: true, message: error instanceof Error ? error.message : "Request failed; no successful outcome established"}); return false; }
    finally { setBusy(false); }
  }
  const props: ScreenProps = {identity: identity as Identity, revision, refresh, mutate, busy};
  async function connect(event: FormEvent) {
    event.preventDefault(); setBusy(true); setSessionError(undefined);
    try {
      const response = await fetch("/api/session", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token})});
      const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? "Identity could not be verified");
      setIdentity(body); setToken(""); refresh();
    } catch (error) { setSessionError(error instanceof Error ? error : new Error("Connection failed")); }
    finally { setBusy(false); }
  }
  if (identity === undefined) return <main className="login"><div className="brand"><CheckCheck /> Resolve<span>OS</span></div><Loading /></main>;
  if (!identity) return <main className="login"><div className="login-panel"><div className="brand"><CheckCheck /> Resolve<span>OS</span></div><p className="eyebrow">OPERATIONS WORKBENCH</p><h1>Evidence to resolution.</h1><p>Connect to your local synthetic operations environment with an authorized employee or worker token.</p><form onSubmit={connect}><label htmlFor="access-token">Authorized development token</label><input id="access-token" type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} required minLength={24} maxLength={4096} /><Button type="submit" disabled={busy}>{busy ? "Verifying identity…" : "Connect to ResolveOS"} <ArrowUpRight size={15} /></Button></form>{sessionError && <Failure error={sessionError} />}<div className="login-note"><ShieldCheck size={18} /><p>Identity and permissions are verified by the backend. Synthetic environment · no live banking.</p></div></div><div className="login-art"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit-core"><CheckCheck size={58} /></div><span>Observe. Review. Verify.</span></div></main>;
  const title = navigation.find(item => item.id === view)?.label ?? "Page unavailable";
  const caseScoped = ["investigations", "timeline", "shadow"].includes(view);
  return <div className="app-shell"><aside className={mobileNav ? "sidebar mobile-open" : "sidebar"}><Link href="/" className="brand"><CheckCheck size={26} /> Resolve<span>OS</span></Link><div className="workspace"><span className="workspace-icon"><Boxes size={17} /></span><div><strong>Operations workspace</strong><small>Synthetic banking</small></div><ChevronDown size={14} /></div><p className="nav-caption">WORKSPACE</p><nav aria-label="Main navigation">{navigation.map((item, index) => <div key={item.id}>{index === 7 && <p className="nav-caption">GOVERNANCE</p>}<Link href={`/${item.id === "overview" ? "" : item.id}${["timeline", "investigations", "shadow"].includes(item.id) && activeCase ? `?case=${activeCase}` : ""}`} className={view === item.id ? "nav-link active" : "nav-link"} aria-current={view === item.id ? "page" : undefined} onClick={() => {setSelectedCase(""); setMobileNav(false);}}><item.icon size={18} />{item.label}</Link></div>)}</nav><div className="sidebar-bottom"><div className="environment-dot" /> Synthetic environment<p>Independent verification establishes resolution.</p></div></aside><div className="main-shell"><header className="topbar"><button className="mobile-toggle" aria-label="Toggle navigation" onClick={() => setMobileNav(!mobileNav)}><PanelLeft /></button><div className="breadcrumb">Workspace <span>/</span> <strong>{title}</strong></div><form className="global-search" onSubmit={e => {e.preventDefault(); router.push(`/cases?q=${encodeURIComponent(search)}`);}}><Search size={16} /><input aria-label="Search cases" placeholder="Search cases…" value={search} onChange={e => setSearch(e.target.value)} /></form><span className="environment-pill">Synthetic</span><div className="avatar"><CircleUserRound size={21} /></div><button className="signout" title="Disconnect" aria-label="Disconnect" onClick={async () => {await fetch("/api/session", {method: "DELETE"}); setIdentity(null);}}><LogOut size={17} /></button></header><main className="content"><div className="page-heading"><div><p className="eyebrow">RESOLVEOS / {identity.roles.includes("OPERATIONS_REVIEWER") ? "EMPLOYEE REVIEW" : "TRUSTED WORKER"}</p><h1>{view === "overview" ? "Operations overview" : view === "cases" && caseId ? "Case workspace" : title}</h1><p>{view === "overview" ? "Current workload, measured outcomes and the evidence behind them." : "Persisted records from the protected operations backend."}</p></div><Button variant="secondary" onClick={refresh} disabled={busy}><RefreshCw size={15} /> Refresh</Button></div>{notice && <div role={notice.error ? "alert" : "status"} className={`notice ${notice.error ? "error" : "success"}`}>{notice.message}<button aria-label="Dismiss message" onClick={() => setNotice(undefined)}>×</button></div>}{caseScoped && <div className="case-selector"><label htmlFor="selected-case">Case workspace</label><DataState state={cases}>{data => <select id="selected-case" value={activeCase} onChange={e => setSelectedCase(e.target.value)}>{data.items.map(item => <option key={item.id} value={item.id}>{item.case_number} · {item.summary ?? label(item.status)}</option>)}</select>}</DataState>{activeCase && <Link href={`/cases/${activeCase}`}>Open case <ArrowUpRight size={13} /></Link>}</div>}
  {view === "overview" ? <Overview {...props} /> : view === "cases" ? caseId ? <CaseView {...props} caseId={caseId} /> : <Cases key={query} {...props} query={query} /> : view === "investigations" ? <Investigations {...props} caseId={activeCase} /> : view === "approvals" ? <Approvals {...props} /> : view === "timeline" ? <Timeline {...props} caseId={activeCase} /> : view === "intelligence" ? <IntelligenceView {...props} /> : view === "shadow" ? <Shadow {...props} caseId={activeCase} /> : view === "memory" ? <Memories {...props} /> : view === "models" ? <ModelLab {...props} /> : <Card title="Page unavailable"><Link href="/">Return to overview</Link></Card>}
  <footer className="page-footer"><span><ShieldCheck size={13} /> {identity.user_id} · {identity.roles.map(label).join(", ")}</span><span>Observed facts · recorded interpretation · hypothetical projections</span></footer></main></div></div>;
}
