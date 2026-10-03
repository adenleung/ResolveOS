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
- Phase 12: dataset-inadequate offline evaluation/governance accepted (311 full / 43 targeted tests); training blocked, trained path unverified, no model enabled. See PHASE12_ACCEPTANCE.md.
- Phase 13: evidence-backed intelligence implemented; acceptance and remote checkpoint in PHASE13_ACCEPTANCE.md.
- Phase 14: shadow isolation, recorded decision replay, outcome comparison and reliability telemetry; validation in PHASE14_ACCEPTANCE.md.
- Phase 15: frontend (not started; excluded).

Current implementation checkpoint: **Phase 14 shadow and reliability**; exact acceptance, migration and remote checkpoint status are in PHASE14_ACCEPTANCE.md. Rules remain active; no ML model is enabled. Source Alembic is `20261004_0013`; development upgrade requires verified backup restoration and unchanged source-row hashes. The authorized recovery build continues through Phase 15 after the separate validated Phase 14 commit and push.

Scheduling, workflow approval, deterministic action authorization, executed effects and independent verification remain distinct. Current remediation is limited to synthetic confirmation replay and never repeats a monetary transfer.

## Expanded feature roadmap (PLANNED, not implemented)

- Phase 12 follow-up within evaluated scope: adequate reviewed datasets and an environment permitting optional ML libraries are needed for real model comparisons; any integration requires separate evidence and approval.
- Phase 13: evidence-backed root-cause hypotheses, process mining, case dependency visualization and approved improvement tracking.
- Phase 14 future extension: production identity/tenancy and distributed failover verification; operational model routing remains unavailable.
- Phase 15: enterprise operations dashboard, evidence-linked human handover and interactive what-if visualization using persisted hypothetical reports.
- Optional Phase 16: Pixel Agents visualization, strictly mirroring real backend state.

These are future phases. No Phase 11–16 work was implemented in the Phase 10 extension.
