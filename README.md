# ResolveOS

Synthetic banking operations prototype: modular FastAPI monolith, PostgreSQL,
versioned APIs, durable fenced workers, deterministic controls, separate human
action approvals, confirmation-only execution, independent verification and
reviewed historical memory. Phases 1–14 are implemented. The authorized recovery
build continues through separately validated Phases 14 and 15.

Phase 12 found inadequate ML data; no trained model is operational. Phase 13 adds
protected read-only operational intelligence. See CURRENT_STATE.md and the phase
acceptance reports for exact results and limitations. No live banking, real customer
data or paid LLM calls are used. Production identity/tenancy and distributed failover
are not claimed.

Phase 14 adds non-executable shadow evaluation and outcome comparison, recorded
decision replay and measured telemetry under `/api/v1/reliability`. See
PHASE14_ACCEPTANCE.md for authority boundaries, historical limitations and migration.

## Backend setup

Use Python 3.11+ (on this machine the executable is
`C:\Users\adenl\AppData\Local\Programs\Python\Python313\python.exe`).
Install `requirements.txt`, start PostgreSQL with `docker compose up -d postgres`,
and copy `.env.example` to an ignored `.env`. Never commit environment secrets.
For a fresh database, apply migrations with `python -m alembic upgrade head`.
An existing development database requires a verified backup before any new migration;
never reset, truncate or downgrade development for tests.

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.orchestration.worker --poll
```

The worker is an explicit trusted process; live AI providers stay disabled by default.
Unavailable handlers remain WAITING_HANDLER rather than fabricating findings.
Health: `/health`, `/ready`. API documentation: `/docs`.

## Local protected APIs

For synthetic local use only, set `APP_ENV=development`,
`ORCHESTRATION_DEV_AUTH_ENABLED=true`, and distinct WORKER/REVIEWER token secrets
of at least 24 characters using the `.env.example` names. Send the correct token
in `Authorization: Bearer ...`. Development identity is refused in production.
Reviewer workflow approval is distinct from action-bound approval and execution.

Operational intelligence reads:

- GET `/api/v1/intelligence/report` (optional start/end/case_limit).
- GET `/api/v1/intelligence/incidents/{incident_id}/relationships`.

Reports have explicit cohort windows, query/reference caps, truncation and evidence
references. Incomplete durations are not completed samples; hypotheses are not
proved causes. Current SLA exposure is not a reconstructed historical breach rate.

## PostgreSQL verification

```powershell
python verify_backend.py --report regression-results.xml
python verify_backend.py --targeted --phase 13 --report phase13-targeted-results.xml
```

Set DATABASE_URL to the local administrative development connection in the process
environment. The verifier creates its own disposable database, migrates and checks
round trips, runs tests, then removes that database on success. Never run destructive
integration fixtures directly against development. Existing Phase 9?12 safety tests
remain required. The PostgreSQL role needs temporary database creation permission.
