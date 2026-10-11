# Offline component-unavailability study

`py -3.13 run_agent_ablation.py`; ten real-service runs on owned PostgreSQL databases:

| Configuration | Family | Case state | Specialist invocations | Tool calls | Supervisor records | Observed seconds |
|---|---|---|---|---|---|---|
| existing-routing | eligible_missing | AWAITING_DECISION | 2 | 2 | 1 | 1.15 |
| existing-routing | technology_timeout | AWAITING_DECISION | 2 | 2 | 1 | 0.8545 |
| omit-transaction | eligible_missing | AWAITING_HUMAN | 2 | 1 | 0 | 0.8318 |
| omit-transaction | technology_timeout | AWAITING_HUMAN | 2 | 1 | 0 | 0.673 |
| omit-technology | eligible_missing | AWAITING_HUMAN | 1 | 0 | 0 | 0.7793 |
| omit-technology | technology_timeout | AWAITING_HUMAN | 1 | 0 | 0 | 0.6492 |
| omit-risk | eligible_missing | AWAITING_DECISION | 2 | 2 | 1 | 0.9871 |
| omit-risk | technology_timeout | AWAITING_DECISION | 2 | 2 | 1 | 0.8523 |
| omit-supervisor | eligible_missing | AWAITING_DECISION | 2 | 2 | 0 | 0.8132 |
| omit-supervisor | technology_timeout | AWAITING_DECISION | 2 | 2 | 0 | 0.6813 |

No action was submitted in this study. Required specialist unavailability fails explicitly and routes to review; absent Supervisor produces no review record, so action controls cannot accept a nonexistent review. Risk omission can be identical to baseline when current routing does not require Risk: this is evidence of selective routing, not proof Risk is unnecessary. Normal routing reaches advisory decision readiness, which is distinct from verified resolution. Mode A versus C in the operational benchmark supplies the rule-covered deterministic comparison.

Retain the existing specialists/Supervisor and routing. No added agent is justified. This is a failure-containment ablation, not a live-model accuracy study or comparison with an optimized single investigator. Two families/one run cannot quantify accuracy, token savings, meaningful latency advantages or broad architecture optimality. Always-all and leaner live configurations remain deferred until a nonleaking held-out accuracy/cost evaluation can support them.
