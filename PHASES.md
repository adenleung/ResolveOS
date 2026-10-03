# Phase roadmap

- Phase 1: backend foundation, lifecycle and audit (implemented).
- Phase 2: synthetic banking environment (implemented).
- Phase 3: observed event ingestion and exception detection (implemented).
- Phase 4: classification, priority, SLA and routing (implemented).
- Phase 5: deterministic incident correlation and lifecycle (implemented).
- Phase 6: durable case orchestration, work queue and workflow review (implemented).
- Phase 7: specialist investigators (implemented with fake-model tests; live-provider integration unverified).
- Phase 8: Supervisor evidence validation and targeted reinvestigation (implemented).
- Phase 9: deterministic controls and action authorization (implemented).
- Phase 10: synthetic confirmation replay, independent verification, terminal execution recovery and counterfactual projections (**0011 PostgreSQL accepted**).
- Phase 11: reviewed operational memory (**0012 PostgreSQL accepted**).
- Phase 12: reproducible ML/correlation benchmarks (not started).
- Phase 13: prevention and analytics (not started).
- Phase 14: dedicated security/reliability acceptance (incomplete; earlier phases provide partial coverage).
- Phase 15: frontend (not started; excluded).

Current accepted checkpoint: **Phase 11**, 268 full regression tests, 46 targeted memory tests and 69 unchanged Phase 9–10 safety tests passing. Fresh and populated migration round trips and reflected constraints/indexes passed. Source and development Alembic are `20261004_0012`; development upgraded after final validation and a fresh recovery backup, with all 38 existing tables preserved by row count and content hash. See CURRENT_STATE.md and PHASE11_ACCEPTANCE.md. Ready for a separately authorized Phase 12 handoff; stop after Phase 11.

Scheduling, workflow approval, deterministic action authorization, executed effects and independent verification remain distinct. Current remediation is limited to synthetic confirmation replay and never repeats a monetary transfer.

## Expanded feature roadmap (PLANNED, not implemented)

- Phase 12: incident-aware benchmarks comparing deterministic rules, Logistic Regression, Decision Tree, Random Forest, XGBoost and LightGBM; only deploy an advisory model if evidence justifies it.
- Phase 13: evidence-backed root-cause hypotheses, process mining, case dependency visualization and approved improvement tracking.
- Phase 14: comprehensive security/reliability tests, Shadow Mode, decision-context replay, incident replay, failure detection and optional model routing.
- Phase 15: enterprise operations dashboard, evidence-linked human handover and interactive what-if visualization using persisted hypothetical reports.
- Optional Phase 16: Pixel Agents visualization, strictly mirroring real backend state.

These are future phases. No Phase 11–16 work was implemented in the Phase 10 extension.
