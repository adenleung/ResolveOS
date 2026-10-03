export type Json = Record<string, unknown>;
export interface Identity { user_id: string; roles: string[]; environment: string; synthetic_only: boolean; live_provider_enabled: boolean }
export interface CaseSummary { id: string; case_number: string; status: string; summary: string | null; priority: string; created_at: string; updated_at: string; sla_deadline: string | null; categories: string[]; incident_ids: string[] }
export interface CasePage { items: CaseSummary[]; total: number; limit: number; offset: number }
export interface Approval { id: string; status: string; assigned_role: string; assigned_user: string | null; expires_at: string }
export interface Authorization { id: string; case_id: string; outcome: string; reasons: string[]; action: Json; approval: Approval | null; created_at: string; expires_at: string; policy_version_id: string | null }
export interface CaseDetail { case: CaseSummary; exceptions: Json[]; assessments: Json[]; evidence: Json[]; investigations: Json[]; supervisor_reviews: Json[]; authorizations: Authorization[]; simulations: Json[]; tasks: { tasks: Json[]; events: Json[] }; policies: Json[]; truncated: boolean }
export interface Reference { id: string; kind: string; case_id: string | null }
export interface Finding { key: string; count: number; case_ids: string[]; references: Reference[]; method: string; limitation: string }
export interface Duration { key: string; completed: number; incomplete: number; invalid_order: number; median_seconds: number | null; maximum_seconds: number | null }
export interface Hypothesis { suspected_factor: string; supporting_evidence: Reference[]; contradictory_evidence: Reference[]; affected_cases: string[]; missing_information: string[]; next_step: string; confidence_limitation: string }
export interface Intelligence { generated_at: string; window_start: string; window_end: string; case_count: number; overview: Record<string, number>; categories: Finding[]; systems: Finding[]; recurrences: Finding[]; bottlenecks: Duration[]; hypotheses: Hypothesis[]; prevention: Hypothesis[]; truncated: boolean; limitations: string[] }
export interface Replay { case_id: string; as_of: string; evidence_known_at_time: Json[]; evidence_observed_later: Json[]; timeline: Json[]; truncated: boolean; reconstruction_limitations: string[] }
export interface ActionReview { kind: string; case_id: string; authorization: Authorization; approval: Approval }
export interface ApprovalPage { actions: ActionReview[]; workflows: Json[]; limit_per_kind: number; offset: number }
export interface MemoryPage { items: Json[]; label: string; limit: number; offset: number }
export interface ModelLab { operational_model_enabled: boolean; runtime_authority: string; checkpoint: string; dataset_readiness: Json; model_comparison: Record<string, Json>; limitation: string }
export function record(value: unknown): Json { return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {}; }
export function rows(value: unknown): Json[] { return Array.isArray(value) ? value.filter(v => v && typeof v === "object" && !Array.isArray(v)) : []; }
export function words(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []; }
export function text(value: unknown, missing = "Unavailable"): string { return typeof value === "string" ? value : typeof value === "number" ? String(value) : missing; }
export function label(value: string): string { return value.replaceAll("_", " ").replaceAll("-", " ").toLowerCase().replace(/^./, c => c.toUpperCase()); }
export function date(value: unknown): string { if (typeof value !== "string") return "Not recorded"; const time = new Date(value); return Number.isNaN(time.getTime()) ? "Not recorded" : time.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
export function seconds(value: number | null): string { if (value === null) return "No completed samples"; return value < 60 ? `${value.toFixed(1)}s` : value < 3600 ? `${(value / 60).toFixed(1)} min` : `${(value / 3600).toFixed(1)} h`; }
