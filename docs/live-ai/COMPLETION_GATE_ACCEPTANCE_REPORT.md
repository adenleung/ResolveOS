# Scenario B completion-gate audit

New live-model tests: **NOT RUN**. No paid calls or credential inspection. Historical live evidence is preserved at `artifacts/20261010T224937-live-49d7e0`.

## Evidence and operational decision

The saved run made four requests and reported 8910 tokens. Transaction completed. Technology returned NEEDS_ADDITIONAL_EVIDENCE with diagnostic logs requested to explain the initial timeout. Six predicates across the specialists were independently supported; none contradicted. Twelve applicable checks passed, three Supervisor checks were NOT RUN, and native orchestration escalated to human review.

There is a second blocker: Technology's combined settled-payment/posted-ledger finding has `field: null`, so it remained NOT_EVALUATED. The six supported predicates do not validate that extra claim or the surrounding prose. Even a hypothetical COMPLETED output would be downgraded while this unverified finding and missing_evidence remain. The model itself requested additional evidence; the gate did not invent a causal-certainty requirement or promote its outcome.

| Decision | Required evidence and meaning |
|---|---|
| Bounded advisory investigation | Establish recorded payment/ledger/acknowledgement discrepancy and gateway observations, identify uncertainty, and provide safe advisory next steps. The B sources suffice for this scope. |
| Definitive root-cause diagnosis | Establish why the endpoint timed out or prove it caused the pending acknowledgement. Internal diagnostic evidence is absent; this objective is not complete. |
| Authorization eligibility | Independently satisfy action-specific policies, source integrity, Supervisor eligibility, approvals and execution fencing. A completed investigator result does not establish any of these. |

The initial HTTP504 and later HTTP200 `/health` observations are different endpoints at different times. They do not conflict as identical source predicates, prove general recovery, establish confirmation receipt, or rule out internal dependencies. Root-cause logs are material to diagnosis and may be material to a particular remedy. They are not inherently necessary to describe this corroborated operational state and recommend diagnostic/operational review. The absence of definitive cause must remain explicit. A specialist can still reasonably escalate if it identifies a material gap for its advisory recommendation; no output is forced complete.

Scenario A's missing confirmation observation and other unknowns remain potentially material. No blanket rule makes unknowns nonblocking, and no Scenario A truth or source data was changed. Scenario B ground truth already states that internal cause is unknown and timeout causation is unproven; it was not rewritten to grade this live result as a pass.

## Audited implementation

`app/investigation/service.py` supplies common read-only instructions plus the investigator role, rather than a distinct Technology completion contract. It previously said to report missing evidence but did not distinguish material assessment gaps from further diagnostic questions. `Output` likewise had undescribed outcome/missing_evidence fields. `Hypothesis.unresolved_questions` already existed.

`validate_output()` already permits unresolved hypothesis questions alongside supported predicates and no material gaps. It downgrades COMPLETED for missing evidence, contradictions, truncation, absent findings or any non-supported finding. It never upgrades NEEDS_ADDITIONAL_EVIDENCE. `coordinate()` waits for all required task results and only schedules Supervisor when every investigator outcome is COMPLETED. Those rules are preserved byte-for-byte.

Minimal correction: clarify the instructions and existing schema descriptions, with specialist prompt version 1.3. COMPLETED means bounded advisory assessment, not proven cause, incident resolution or authorization. Nonblocking diagnostic questions belong in hypotheses; material gaps remain missing_evidence and block completion. Atomic field predicates replace composite multi-field claims. No new output field or relaxed evidence requirement was introduced.

A focused regression exposed a separate uncertainty-propagation defect: accepted specialist hypotheses persisted in investigator results but were omitted from the Supervisor snapshot. Supervisor now receives their existing supporting/contradicting references mapped to independently checked stored evidence IDs, together with unresolved questions and an explicit UNVERIFIED_INTERPRETATION label. Invalid mappings fail closed. The persisted Supervisor result retains this context even when model prose omits it; it is not inserted into supported_conclusions. Supervisor instructions explain that this context is neither established causation nor action eligibility (prompt version 1.1). This adds internal snapshot/result context without changing the protected request/structured-output fields or completion rules.

Deterministic authorization and execution services are unchanged. Neither AI output can set action_authorization other than NOT_EVALUATED. Supervisor recommendations remain advisory and cannot execute; action-specific uncertainty must still constrain recommendations and independent controls. A cause unknown does not universally prove or disprove eligibility for every possible action.

## Reproduction and regression evidence

Before the correction: four semantics checks passed; two failed, reproducing the missing contract clarification and missing Supervisor hypothesis context; [JUnit](artifacts/completion-semantics-before.xml). The already-passing test confirms that causal uncertainty itself was never a validator completion requirement.

The saved live Technology output is preserved in `tests/fixtures/scenario_b_live_completion_gap.json` and revalidated offline. It remains NEEDS_ADDITIONAL_EVIDENCE and retains the NOT_EVALUATED finding; this fix does not retrospectively change the observed live outcome.

Regression coverage includes supported advisory completion with unresolved diagnostic questions, retained material gaps, retained model-selected incomplete status, composite findings remaining unverified, attempted authorization rejection, native Supervisor receiving/persisting uncertainty, no actions or ledger changes, and both Scenario A/B paths. Existing phases 7–9 retain wrong citations, temporal controls, leases, source changes, disagreement, approval and authorization tests.

Final test counts and archive evidence are recorded in the verification addendum below. No claim is made that changed instructions improve GPT behavior until a new explicitly authorized live run supplies evidence.

## Verification addendum

- Final PostgreSQL phases 7–9 plus grounding, runner, both scenarios and semantics: **121 passed**, zero failures, in 261.04 seconds; [JUnit](artifacts/completion-semantics-postgres.xml). Fresh migration upgrade/downgrade/upgrade and owned-database cleanup passed.
- Final focused runner/grounding/semantics tests: **60 passed**, zero failures, in 28.55 seconds; [JUnit](artifacts/completion-semantics-unit.xml). This additionally includes saved Scenario B output revalidation and attempted authorization rejection, added after the larger batch collected its tests.
- Foreign specialist hypothesis reference: **1 passed** in a fresh disposable database; [JUnit](artifacts/completion-semantics-foreign-reference.xml). The Supervisor provider is never invoked for this invalid context.
- Native uncertainty rehearsal: [REPORT](artifacts/completion-semantics-uncertainty-native/uncertain-complete/REPORT.md), [results](artifacts/completion-semantics-uncertainty-native/uncertain-complete/results.json). Both supported advisory investigations completed, native orchestration scheduled Supervisor, unresolved diagnostic questions reached it and remained in its persisted result. All 15 automated checks passed; action/approval/authorization/operation/verification tables stayed empty, bank records were unchanged, and the database was dropped. These are deterministic fixture results, not GPT-quality evidence.
- [Integrity](artifacts/completion-semantics-integrity.json): comparison with the preserved Phase 17 ZIP confirms the validator, tools, orchestration service/queue, deterministic control service and execution service are byte-for-byte unchanged. The native coordinate method is unchanged. All 54 frozen frontend files match baseline bytes. Historical live reports are untouched.

Acceptance: the semantics clarification and uncertainty propagation pass the stated offline scope. The actual saved live result remains incomplete and correctly escalated under its declared missing evidence and unverified composite finding. Revised GPT behavior and live Supervisor completion are **NOT RUN**. No production-readiness claim or automatic paid rerun is made.
