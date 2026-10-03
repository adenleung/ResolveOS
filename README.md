# ResolveOS

ResolveOS is a modular monolith for synthetic banking operations. Phases 1-8 implement observed events, detection, classification, correlation, durable orchestration, restricted investigators and independent Supervisor review. Controls/remediation and Phases 9-14 remain unfinished; the frontend is excluded.

AI tests use deterministic fake models. Live OpenAI execution is disabled by
default and has not been tested against the real provider. PostgreSQL regression
and fresh migration verification: `py verify_backend.py`; targeted Supervisor
tests: `py verify_backend.py --targeted --phase 8`. See CURRENT_STATE.md for
verified results and PHASE9_CONTRACTS.md to resume development.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL-ready configuration
- Pytest
- Docker Compose for local Postgres

## Quick start

1. Create a virtual environment.
2. Install dependencies:
   ```bash
   py -m pip install -r requirements.txt
   ```
3. Copy the sample environment file:
   ```bash
   copy .env.example .env
   ```
4. Apply migrations, then run the app:
   ```bash
   py -m alembic upgrade head
   uvicorn app.main:app --reload
   ```
5. Validate health checks:
   ```text
   http://localhost:8000/health
   http://localhost:8000/api/v1/health
   http://localhost:8000/ready
   ```

## Local PostgreSQL

The repository includes a Docker Compose configuration for a local Postgres instance:

```bash
docker compose up -d postgres
```

## Testing

```bash
py -m pytest -q
```

## Notes

Development stops after Phase 6. AI investigators, Supervisor, controls/authorization, banking remediation, ML and frontend remain deferred.

## Durable orchestration

```bash
py -m app.orchestration.worker --poll --once
py -m app.orchestration.worker --poll
```

The CLI is a trusted local database process. It handles classification, routing, re-evaluation and SLA checks; future tasks remain `WAITING_HANDLER` without fabricated success.

HTTP orchestration/review access is disabled by default. For local use, set `ORCHESTRATION_DEV_AUTH_ENABLED=true`, configure distinct `ORCHESTRATION_DEV_WORKER_TOKEN` and `ORCHESTRATION_DEV_REVIEWER_TOKEN` secrets of at least 24 characters, and use `APP_ENV=development` or `test`. Send `Authorization: Bearer ...` with the appropriate secret. Production use of this identity mechanism is refused. Do not commit real secrets.

For a full PostgreSQL regression against a fresh isolated database, including migration downgrade/upgrade:

```bash
py verify_phase6.py
```

The configured database role needs temporary database creation permission. The script deletes its own verification database on success and retains it on failure. Results are written to `phase6-test-results.xml` and `phase6-workload-results.json`. Regular `pytest` requires PostgreSQL `DATABASE_URL` in the process environment to run integration tests.

See ARCHITECTURE.md for endpoints, leases and operational limits; PHASE7_CONTRACTS.md for investigator contracts.
# ResolveOS
