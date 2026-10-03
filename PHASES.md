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
- Phase 15: protected nine-module operations workbench and three persisted isolated demos accepted; see PHASE15_ACCEPTANCE.md.

Current implementation checkpoint: **Phase 15 operations workbench**; exact acceptance, migration and remote checkpoint status are in PHASE14_ACCEPTANCE.md. Rules remain active; no ML model is enabled. Source Alembic is `20261004_0013`; development upgrade requires verified backup restoration and unchanged source-row hashes. Phase 15 was built after the separately validated, pushed and verified Phase 14 checkpoint.

Scheduling, workflow approval, deterministic action authorization, executed effects and independent verification remain distinct. Current remediation is limited to synthetic confirmation replay and never repeats a monetary transfer.

## Expanded feature roadmap (PLANNED, not implemented)

- Phase 12 follow-up within evaluated scope: adequate reviewed datasets and an environment permitting optional ML libraries are needed for real model comparisons; any integration requires separate evidence and approval.
- Phase 13 future extension: approved improvement tracking and deeper process mining.
- Phase 14 future extension: production identity/tenancy and distributed failover verification; operational model routing remains unavailable.
- Phase 15 future extension: enterprise identity and deployment hardening; the protected synthetic workbench is implemented.
- Optional Phase 16: Pixel Agents visualization, strictly mirroring real backend state.

These are future phases. No Phase 11–16 work was implemented in the Phase 10 extension.
