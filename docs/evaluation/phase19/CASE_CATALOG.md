# Pilot case catalog
All ten cases are development fixtures, not held-out cases. Identities and source records vary each run. Source truth and expert materiality are frozen separately before provider use.

| Case | Family | Decision | Specialist runs | Supervisor |
|---|---|---|---|---|
| P19-01 | delayed-ack | COMPLETE | 2 | COMPLETED |
| P19-02 | missing-authority | ESCALATE | 2 | NOT RUN |
| P19-03 | financial-disagreement | ESCALATE | 2 | NOT RUN |
| P19-04 | duplicate-risk | ESCALATE | 2 | NOT RUN |
| P19-05 | retry-lifecycle | COMPLETE | 2 | COMPLETED |
| P19-06 | source-conflict | ESCALATE | 0 | NOT RUN |
| P19-07 | api-degradation | COMPLETE | 1 | COMPLETED |
| P19-08 | late-ledger-correction | COMPLETE | 2 | COMPLETED |
| P19-09 | policy-restricted | ESCALATE | 2 | NOT RUN |
| P19-10 | stale-workflow | NO_EXCEPTION | 0 | NOT APPLICABLE |

P19-04 represents a duplicate-risk normalized observation, not two accepted instructions with the same unique key. Only the primary payment is seeded in the simulator. P19-06 is genuine native human triage before specialist execution. P19-10 is a negative control: a newer completed workflow supersedes the old state before detection. P19-08 substitutes late ledger correction for an unsupported WORKFLOW investigator; no handler was invented. P19-09 installs and reads an existing valid policy but cannot authorize. Risk's unavailable policy-applicability connector remains unavailable.

[Native offline results](artifacts/20261011T044418-offline-d5f38f/results.json) and [rules results](artifacts/20261011T044418-rules-f894fa/results.json).
