# Phase 11 acceptance checkpoint — 2026-10-04

**Phase 11 acceptance is complete for the documented synthetic scope.** All
required validation passed and development was upgraded after a recovery backup.
Ready for a separately authorized Phase 12 handoff. Phase 12 remains unstarted.

## Verified starting checkpoint

The existing Phase 10 reports contain 29 targeted and 222 full tests with no
failures/errors/skips. Alembic source and the actual development database were
confirmed at `20261002_0011`. These original XML reports remain unchanged.
The actual memory tool was unimplemented; independent synthetic verification
records and their operation/action/authorization chain were inspected before coding.
Git executable and repository are unavailable; no commit is claimed.

## Validation

| Ordered check | Result | Evidence |
| --- | --- | --- |
| Existing investigator and Supervisor baseline | 39 passed, 138.213s | phase11-existing-investigators-results.xml |
| Final Phase 11 targeted PostgreSQL | 46 passed, 160.077s | phase11-test-results.xml |
| Existing Phase 9–10 safety and simulation | 69 passed, 180.255s | phase11-safety-results.xml |
| Complete PostgreSQL regression | 268 passed, 666.314s | phase11-full-regression-results.xml |
| Fresh database migration | 0001 -> 20261004_0012 passed | phase11-migration-results.json |
| Populated 0012 downgrade/re-upgrade | Passed; 38 source/audit tables preserved by row counts/hashes | phase11-migration-results.json |
| Reflected constraints and indexes | Passed; types, nullability, PK/FK/unique/check/index definitions match models | phase11-migration-results.json |
| Development backup and 0011 -> 0012 | Passed; all 38 existing tables preserved by row counts/hashes | phase11-development-migration-results.json |

Durations in this table are exact JUnit report values. The console reported
138.22s, 160.08s, 180.25s and 666.32s respectively. The final full suite contains
all original 222 accepted tests plus 46 new tests. No existing test was weakened.

The baseline run produced one optional pytest-cache write-permissions warning.
Subsequent runs disable only pytest's optional cache plugin; test assertions and
application warnings are not suppressed. Final targeted, safety and full runs have no
failures/errors/skips/warnings. Every verifier uses a fresh disposable database,
applies the complete migration chain, downgrades to 0006 and re-upgrades before
tests. Successful disposable databases are removed.

An initial 40-test Phase 11 run produced 39 passes and one new HTTP-test failure:
it assumed a nonexistent get_settings cache. The test was corrected to use the
actual uncached factory; existing tests were not modified. A subsequent 44-test
run passed in 176.89s; two draft-correction checks completed the final 46-test
targeted suite. After final passing validation, the diagnosed failed disposable
database was verified empty and removed; its local marker was removed as well.

## Migration, backup and retrieval measurement

Source and development are at `20261004_0012`, whose parent is exactly
`20261002_0011`. The dedicated verifier seeded an actual independently verified
synthetic case and reviewed active memory, retrieved it, downgraded only Phase 11,
and re-upgraded. All 38 source/audit tables retained identical row counts and
full-row SHA-256 hashes. Downgrade explicitly removed the five memory tables;
re-upgrade recreated them empty. Earlier verifier runs also checked downgrade to
0006 and re-upgrade on empty disposable schemas.

Before development upgrade, the guarded script verified final regression reports,
the populated migration report, the development revision and PostgreSQL cluster
identity. It created `resolveos-pre-0012.dump` in custom archive format and checked
its TOC with pg_restore --list. It then upgraded only 0011 -> 0012 and verified
unchanged counts/content hashes in all 38 existing application tables. Five new
memory tables are empty. Development was never reset or downgraded. Backup hash
and before/after evidence are in phase11-development-migration-results.json.
Backup restoration was not rehearsed; archive listing and schema round trips are
the checks performed. The backup is local and ignored by .gitignore.

An actual candidate-query EXPLAIN (ANALYZE, BUFFERS) used `ix_memory_retrieval`
and `operational_memories_pkey`. A single local synthetic retrieval returned one
eligible memory, **1,772 serialized JSON bytes**, using **24 SQL statements**
including trust rechecks/audit, in **0.132026s**. Evidence reads are batched per
candidate. This verifies a small local sample, not enterprise scalability; cost
can grow within the fixed 50-candidate/20-reference caps. Full query plan and
measurement are saved in phase11-migration-results.json.

## Implemented capabilities and safety

- Candidate -> pending human review -> active publication; explicit rejection,
  revocation, approval withdrawal, flagging, corrections and atomic supersession.
- Trust requires the resolved source case, latest independent success, actual
  verified execution/action, bound deterministic authorization, valid action
  approval where needed, intact evidence/events and current memory governance.
- Human summary and source-reference corrections create new candidate versions;
  reviewer history, content hashes and existing audit preserve actor/time/reason.
  Concurrent reviewers cannot publish conflicting versions; rollback preserves
  pending state and prevents partial approval/audit/supersession.
- Five PostgreSQL tables reuse existing source identifiers as FKs, with lifecycle,
  summary/version bounds, family/version uniqueness, one-active-version partial
  uniqueness and indexed bounded retrieval. Banking documents are not duplicated.
- Category-filtered retrieval considers at most 50 active candidates, ranks by
  shared source systems then stable recency/ID, returns default 5/max 10, and
  enforces default 8,000/max 16,000 serialized JSON bytes with truncation.
- Invalid/revoked/corrected source support fails closed immediately. Authorized
  reconciliation persists revocation. Relevant policy changes preserve facts but
  mark guidance outdated; unrelated policy changes do not invalidate records.
- Risk's existing tool performs optional cached retrieval; failed/missing memory
  preserves investigation. Successful reuse still queries current sources.
- Every result labels historical context, has empty current evidence, and retains
  NOT_EVALUATED action authorization. Historical references cannot satisfy current
  finding validation/materialization. Supervisor and current controls remain intact.
- Server-issued roles and explicit case/source grants control access. Model and
  HTTP role claims cannot grant permission; production has no broad default grant.
- No banking-write/execution/approval capability, paid LLM calls, vector/embedding
  dependencies, model training, frontend or real integrations are added.

## Known limitations

- Eligibility is limited to the existing independently verified synthetic
  confirmation workflow. Failed/inconclusive cases remain ordinary history,
  never verified-resolution memory. General verified outcomes need new contracts.
- The schema has no enterprise tenants or production identity provider. Existing
  development roles have broad case access; production needs a trusted adapter
  deriving explicit tenant/user/case/source grants. Scope tests are not proof of
  enterprise tenancy or deployment readiness.
- Reviewer prose is untrusted historical interpretation. Similarity does not
  verify causation. Current source queries, policy controls, human action approval
  and independent verification remain mandatory.
- Matching uses structured category/source overlap and a bounded newest-candidate
  window. Older useful records may be omitted; no enterprise latency/load guarantee
  is claimed. Investigator SQL has a one-second per-statement timeout, not a total
  request latency guarantee. No extra memory call occurs unless requested.
- Relevant policy hashes conservatively mark remediation outdated if any of that
  policy's version/content/effective-window changes; historical facts remain.
- Invalidation is checked on retrieval and persisted by explicit reviewer
  reconciliation. There is no background invalidation daemon. Cached tool results
  are per-attempt historical snapshots and never current permission.
- Database administrators can bypass application history/immutability safeguards.
  Downgrade explicitly deletes memory artifacts and requires backup to restore;
  Phase 1–10 source records and existing audit entries are preserved.
- Summaries are supplied through governed employee/service workflows; no automatic
  AI publication or model retraining exists. Live-provider testing remains deferred.

## Files created or modified

Created:

- app/memory/__init__.py, contracts.py, models.py, service.py, api.py
- alembic/versions/20261004_0012_reviewed_memory.py
- tests/test_phase11_postgres.py
- verify_phase11_migrations.py, apply_phase11_checkpoint.py
- PHASE11_CONTRACTS.md, PHASE11_ACCEPTANCE.md
- Separate Phase 11 test/migration reports listed above; development backup is local/ignored.

Modified:

- app/investigation/tools.py, service.py, contracts.py
- app/orchestration/worker.py, app/main.py, app/database.py, alembic/env.py
- CURRENT_STATE.md, ARCHITECTURE.md, PHASES.md, CHANGELOG.md, MASTER_BUILD_SPEC.md
- PHASE7_CONTRACTS.md, PHASE8_CONTRACTS.md, .gitignore

## Phase 12 handoff

Phase 11 provides governed historical context and review provenance. Phase 12 may
separately design reproducible advisory ML/correlation benchmarks with independent
authorization and privacy/data-quality review; none is implemented here. Do not
automatically consume feedback as training data. Stop after Phase 11.
