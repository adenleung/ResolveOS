# Headless backend acceptance

`py -3.13 run_headless_demo.py --scenario all` freshly migrates an owned disposable PostgreSQL database, uses app/demo and the actual ingestion, detection, classification, incident correlation, orchestration, specialist, Supervisor, controls, reviewer, execution and verification services, and removes the database on exit. No second engine or frontend is introduced. Source generation is deterministic synthetic seeding; record IDs/timestamps are observed, not fabricated. The recorded correlation run examines three cases/two pairs and correctly leaves all three ungrouped; shared endpoints alone do not establish a common incident. Its opt-in demo hook preserves the original default, and the four Phase 15 demo/API compatibility tests were rerun afterward.

| Scenario | Observed case state | Tasks | Evidence records | Successful independent verifications |
|---|---|---|---|---|
| A | RESOLVED | 12 | 4 | 1 |
| C | AWAITING_DECISION | 10 | 3 | 0 |
| B | AWAITING_HUMAN | 8 | 2 | 0 |
| duplicate-request | RESOLVED | 8 | 4 | 1 |
| worker-interruption | RESOLVED | 8 | 4 | 1 |
| verification-failure | ESCALATED | 9 | 4 | 0 |
| missing-handler | INVESTIGATING | 6 | 3 | 0 |

Named CLI scenarios: verified-resolution, contradictory-evidence, stale-authorization, duplicate-request, worker-interruption, verification-failure and missing-handler. JSON exports source IDs/timestamps, task events, specialist findings, Supervisor conclusions, controls, approvals, operation/effect identity, verification detail and audit transitions. Intelligence is calculated by the existing service. Unsupported workflow/document handlers remain WAITING_HANDLER even with available specialist providers. Case state INVESTIGATING is distinct from the unsupported task's waiting status.

The interruption scenario expires a real durable claim and recovers it. Full regression additionally kills ownership through failure injection, proves stale commits roll back, and runs separate worker processes. This runner does not claim a mid-effect OS process kill; that remaining recovery experiment is in the gap register.

`py -3.13 verify_hardening_runtime.py` also starts a real Uvicorn process, checks /health and /ready over loopback HTTP, starts the real one-shot worker subprocess, and runs read-only diagnostics on another empty migrated database. Output: artifacts/runtime-smoke.json. API role/contract checks are in the final regression, including Phase 15. Full frontend-to-PostgreSQL browser acceptance remains unperformed; the frontend was frozen.
