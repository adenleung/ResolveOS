# Cost and efficiency

| Mode | Scripted review decisions | Modelled human seconds | Modelled human-only SGD / verified | Measured total cost |
|---|---|---|---|---|
| A | 9 | 17640 | 4.2 | unmeasured |
| B | 101 | 23160 | 5.5143 | unmeasured |
| C | 9 | 17640 | 4.2 | unmeasured |

Human assumptions: 60 active seconds per meaningful synthetic review, 300 seconds per unresolved human-route case, SGD 30/hour. Include all cohort handling costs in the numerator and independently verified cases only in the denominator. Zero denominators return null. These are transparent assumptions; there is no observed employee study or measured financial saving.

Live input/output tokens, model calls, API prices and infrastructure resource cost are not measured. Offline telemetry's default zero tokens denotes no actual model usage and cannot be treated as measured model efficiency. Benchmark providers make no paid calls. Modelled human-only cost excludes infrastructure and does not equal total cost per resolution. Completed processing latency and censored observations are separate in operational.json.

Existing bounded tool result caching, selective specialists, scoped snapshots, candidate/result/byte limits, iteration/tool/time/usage/cost preflight caps remain. No prompt expansion, new AI call, neural memory or additional agent was introduced. Option B adds bounded structured source queries and measured experimental latency/bytes; runtime default remains original. Valid optimization should be guided by a live-model and operator study, not default-zero telemetry.
