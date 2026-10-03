# Phase 15 acceptance

The operations workbench is implemented over actual persisted backend evidence.
Phase 14 was pushed and remotely verified at
`6095349df3f18ec76f2e73d52e4155d3e3c199c8` before Phase 15 began.

## Validation

- Fresh disposable PostgreSQL: four targeted tests and 354 full regression tests
  passed, with zero failures, errors or skips. The full run took 778.99 seconds.
- Strict TypeScript, ESLint, eight frontend unit tests and production Next.js build
  passed. Exact command timings are in `phase15-frontend-validation.json`.
- Nine browser acceptance checks cover actual data, source inspection, persisted
  human assignment, shadow/replay, memory, unavailable ML, role denials, foreign
  origin rejection, blocked execution, explicit backend failures and mobile layout.
  The overview also passes automated WCAG 2 A/AA accessibility checks.
- `phase15-npm-audit.json` records zero dependency vulnerabilities at acceptance.
- Development remains at migration `20261004_0013`: all 44 application tables,
  containing 76 existing rows, retain identical full-row hashes. Phase 15 adds no
  migration. Demo data lives in a separate generated PostgreSQL database.

JUnit reports and screenshots are committed alongside the source. Initial browser
checks found a canonical-origin mismatch, selector ambiguity and text contrast
issues; these were corrected before the passing acceptance runs.

## Delivered behavior

Overview, Case Centre, Investigations, Approvals, Timeline, Intelligence, Shadow,
Memory and Model Lab use protected APIs, with loading, empty, error and denied
states. Evidence, assessments, policy/control snapshots, investigator findings,
independent verification and historical memory remain inspectable. Charts use
bounded observed cohorts; incomplete durations and truncation remain explicit.

The server-side frontend proxy uses an HttpOnly SameSite Strict session cookie,
explicit canonical-origin checks and a route whitelist. Tokens never enter browser
local storage. Mutations retain backend role, freshness and authority checks.
Reviewer approval, worker execution and independent verification are separate.
No UI action bypasses deterministic controls or invokes public simulator writes.

## Persisted demonstration

`phase15-demo-results.json` contains actual database IDs and observed assertions.
Journey A is independently verified RESOLVED after one confirmation replay; duplicate
delivery/submission produces one effect. Journey B has conflicting evidence and
remains AWAITING_HUMAN. Journey C had human approval, then its policy became inactive:
submission was rejected as stale and the new control outcome is BLOCKED, with no
execution. Its case state remains AWAITING_DECISION, distinct from control status.
Bank amounts and ledger balances remain unchanged.

The offline demo providers inspect real synthetic source tool outputs; no paid LLM
or live bank calls occur. Reviewed memory is historical guidance, not current case
evidence or action authority. Model Lab reads actual saved Phase 12 artifacts and
clearly reports inadequate training data and unavailable native ML. No trained
model is operational. Historical policy contents cannot always be reconstructed;
replay marks that limitation rather than inventing past decision inputs.

This is a local synthetic prototype. Enterprise identity, tenancy, real bank
integration, distributed production failover and operational ML are not claimed.
