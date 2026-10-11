# Fresh full test matrix

Baseline: 354 passed, 0 failed, 0 skipped. Targeted control/execution/hardening gate: 69 passed, no failures/skips. Final isolated PostgreSQL suite: **377 passed, 0 failed, 0 skipped**. A second full run in a newly installed isolated Python environment also passed **377**, with no failures/skips, on another freshly migrated database. Exact JUnit and safe logs are in artifacts; test-matrix.json lists every collected case and observed duration. Historical reports remain separate at project root.

| Test module | Collected cases | Result |
|---|---|---|
| tests.test_audit | 1 | PASS |
| tests.test_case_lifecycle | 2 | PASS |
| tests.test_config | 2 | PASS |
| tests.test_database | 1 | PASS |
| tests.test_foundation_integration | 3 | PASS |
| tests.test_hardening_grounding | 6 | PASS |
| tests.test_hardening_metrics | 6 | PASS |
| tests.test_hardening_postgres | 11 | PASS |
| tests.test_phase10_postgres | 29 | PASS |
| tests.test_phase10_simulation_unit | 16 | PASS |
| tests.test_phase11_postgres | 46 | PASS |
| tests.test_phase12_postgres | 4 | PASS |
| tests.test_phase12_unit | 39 | PASS |
| tests.test_phase13_postgres | 21 | PASS |
| tests.test_phase14_postgres | 18 | PASS |
| tests.test_phase15_postgres | 4 | PASS |
| tests.test_phase2_postgres | 8 | PASS |
| tests.test_phase3_postgres | 13 | PASS |
| tests.test_phase4_postgres | 18 | PASS |
| tests.test_phase5_postgres | 26 | PASS |
| tests.test_phase6_postgres | 35 | PASS |
| tests.test_phase7_postgres | 28 | PASS |
| tests.test_phase8_postgres | 11 | PASS |
| tests.test_phase9_postgres | 24 | PASS |
| tests.test_postgres_integration | 5 | PASS |

Layers: unit, real PostgreSQL integration, migration round trip, API roles/contracts, independent connections and processes, fault/lease/retry injection, source/effect integrity, offline provider and grounding, memory governance, intelligence, ML and shadow/replay. New regressions add conflict replay, strict JSON scalar identity, six-way receipt concurrency, snapshot-time publication exclusion, invalid windows, incomplete citations, typed equality, changed ledger balance, empty denominators/censoring and inspectable ranking.

Separate executed artifacts: seven headless source-to-outcome journeys; 300 matched offline benchmark observations; 30 AI contracts; four-memory/12-query retrieval experiment; ten component-unavailability runs; real HTTP/worker runtime smoke. These are additional experiments, not added to pytest pass totals. Frontend preservation: 54 byte-identical files; no frontend test or browser acceptance newly claimed.

Failures retained: grounding reproduction 1 failed/5 passed before fix; initial benchmark fixture-detection failure; smoke false closure on balance changes; initial diagnostics typo corrected before passing runtime validation. These were repaired without removing assertions or adjusting expected safety outcomes. New critical balance safety acceptance was rerun before benchmark acceptance. Full-suite wall-clock time varies by local load/connection conditions and is not a throughput benchmark.
