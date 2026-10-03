# Recovery build handoff: Phases 13–15

The recovered baseline was Phase 12 commit `f0ed616ff2462602fbd538ec67f9b59bb2c61292`.
Reported newer checkpoints and frontend files were not recoverable; recovery was
built and verified from that baseline without weakening existing safety tests.

| Phase | Accepted checkpoint | PostgreSQL validation |
| --- | --- | --- |
| 13 | `ba0367d46260b9195b1506ebfb79a973ad98465b` | 21 targeted; 332 full |
| 14 | `6095349df3f18ec76f2e73d52e4155d3e3c199c8` | 18 targeted; 69 safety; 350 full |
| 15 | Final repository HEAD; final GitHub SHA supplied with delivery | 4 targeted; 354 full |

Phases 13 and 14 were separately committed, pushed and remotely verified before
the next phase started. Every final test above passed without errors or skips.
Frontend acceptance additionally includes eight unit tests, nine production browser
tests, type checking, lint, production build and a zero-vulnerability npm audit.
Exact results are in the phase acceptance documents and committed XML/JSON reports.

## Start the accepted local demo

Run commands from the repository root. Use Python 3.11+ and Node.js LTS; this
machine uses Python 3.13 and verified portable Node 24 under ignored `.tools`.
Install Python requirements and run `docker compose up -d postgres` first.
The local PostgreSQL administrative connection is port 5433; the unrelated port
5432 database is not used. The existing development database must already be at
`20261004_0013`; verified migration evidence is in the Phase 14 acceptance report.

```powershell
$env:DATABASE_URL='postgresql+psycopg://resolve:resolve@localhost:5433/resolveos'
python verify_phase15_demo.py
cd frontend
npm ci
npm run build
cd ..
```

The verification command creates a new isolated demo database and proves existing
development rows are unchanged. It refuses to seed a nonempty demo. It writes an
ignored `.env.demo` containing generated local authentication tokens; keep this
file local. On this machine, replace `python` with
`C:\Users\adenl\AppData\Local\Programs\Python\Python313\python.exe` if needed.

Run each service in a separate terminal from the repository root:

```powershell
python run_demo_service.py backend
python run_demo_service.py worker
python run_demo_service.py frontend
```

Open `http://127.0.0.1:3000`. Copy the reviewer token from the local `.env.demo`
into the login form to inspect and review; use the worker token for trusted worker
controls. The helpers use only the isolated demo database and disable live AI.
Do not mix this demo worker with a development or production database.
For a different frontend domain configure `RESOLVEOS_FRONTEND_ORIGIN` on its server;
configure `RESOLVEOS_BACKEND_URL` there too. Backend development token authentication
is refused in production; deployable enterprise authentication is future work.

## Walk through the actual journeys

1. Case Centre: search `RECOVERY-A`, inspect normalized source evidence, investigator
   findings, controls and simulation. Its action and operation are VERIFIED and the
   independent verification establishes RESOLVED. Timeline separates hypothetical
   simulation from recorded execution and verification.
2. Search `RECOVERY-B`: conflicting bank/confirmation facts retain AWAITING_HUMAN.
   Approvals allows a reviewer to assign the actual handover and inspect attributed
   history. Review actions require reasons and retain backend authority checks.
3. Search `RECOVERY-C`: inspect prior approval and inactive policy. Current controls
   show BLOCKED and submission is disabled; direct stale submission is rejected by
   the backend too. The action list is empty and no monetary transfer is performed.
4. Intelligence and Shadow show real bounded evidence and non-executable evaluation;
   Memory shows independently sourced reviewed history. Model Lab reports the saved
   dataset-inadequate checkpoint without fabricated trained metrics.

`python -m app.demo` verifies the existing manifest without reseeding or executing.
The seeded demonstration has one operational action and one independent success;
ledger values and payment amounts are unchanged. Generated IDs are recorded in
`phase15-demo-results.json`, not hardcoded as frontend fallback responses.

## Main source and verification files

- Phase 13: `app/intelligence/`, `tests/test_phase13_postgres.py`.
- Phase 14: `app/reliability/`, `app/controls/service.py`, migration
  `20261004_0013`, `tests/test_phase14_postgres.py`,
  `verify_phase14_development_migration.py`.
- Phase 15: `app/workbench/`, `app/demo.py`, `app/main.py`, all `frontend/` source,
  `tests/test_phase15_postgres.py`, `verify_frontend.py`,
  `verify_phase15_demo.py`, `run_demo_service.py`, acceptance reports and screenshots.

```powershell
python verify_backend.py --report phase15-final-full-regression-results.xml
python verify_frontend.py
cd frontend
npm run test:e2e
```

Backend verification creates and removes its own disposable PostgreSQL database;
never run destructive integration fixtures directly against development. Browser
checks require the isolated demo backend and production frontend running and Edge
installed. They persist a real handover assignment and remain repeatable.

The delivered source ZIP is created from final Git HEAD, checked for ZIP integrity
and required backend/frontend files. It excludes credentials, local environment
files, database dumps, dependencies and build output. Restore dependencies and
create a fresh isolated demo using the commands above.
