const reads = [
  /^workbench\/(identity|cases|approvals|memories|model-lab)$/,
  /^workbench\/cases\/[\w.-]+$/,
  /^intelligence\/report$/, /^intelligence\/incidents\/[\w.-]+\/relationships$/,
  /^reliability\/telemetry$/, /^reliability\/cases\/[\w.-]+\/(shadow|shadow-comparison|replay)$/,
  /^cases\/[\w.-]+\/(actions|authorizations|orchestration|tasks|investigations|investigation-evidence|supervisor-reviews|memory|memory\/retrieve)$/,
  /^(reviews|action-approvals)\/[\w.-]+\/history$/, /^memory\/versions\/[\w.-]+\/history$/,
];
const writes = [
  /^cases\/[\w.-]+\/(controls\/evaluate|orchestrate|memory\/candidates)$/,
  /^reliability\/cases\/[\w.-]+\/shadow$/,
  /^action-approvals\/[\w.-]+\/decision$/, /^reviews\/[\w.-]+\/(assign|decision)$/,
  /^authorizations\/[\w.-]+\/simulate$/, /^actions\/submit$/,
  /^memory\/versions\/[\w.-]+\/(review|reconcile)$/,
];
export function allowed(path: string, method: string): boolean { return (method === "GET" ? reads : method === "POST" ? writes : []).some(pattern => pattern.test(path)); }
export function sameOrigin(origin: string | null, url: string): boolean { return origin !== null && origin === new URL(url).origin; }
