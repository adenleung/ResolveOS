# Reproduce Phase 19
From ResolveOS, use the existing Python 3.13 backend dependencies and local PostgreSQL configuration. No new dependencies or manual migrations are needed. Supply DATABASE_URL through your existing local environment; the runner creates/drops fresh owned databases only. Run with the existing backend interpreter (py -3.13 works in this workspace):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track offline
py -3.13 -m scripts.run_evaluation_benchmark --track rules
```

Inspect the printed directory's REPORT.md/results.json, then each case's ground truth, frozen source records, rules-baseline.json, manual-review.json and requests.jsonl. Nonzero exit means incomplete or failed evaluation. Offline is the default and never validates GPT quality.

External reviewed suites use --manifest PATH with phase19-suite-manifest-1.0, benchmark_version, and cases. Each case declares id, family, split, ground_truth, initial_sources and subsequent_sources. Ground truth requires the existing pilot truth fields. Source templates use registered payload fields, minutes_before >= 0, and optional exact $ENTITY/$TRACE/$KEY/$REF_name identity tokens. Families must belong to exactly one split; max 50 cases. This interface is tested, but no held-out evaluation is claimed.

Do not execute live unless separately authorized. After such authorization, one bounded case in your own environment with its existing key can be selected explicitly:

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-05 --authorize-paid-cases 1 --batch-max-requests 10 --batch-max-tokens 120000 --batch-max-usd 0.15
```

The command itself is a paid opt-in; it was NOT RUN here. No key argument or file is used. Legitimate incomplete model output remains human escalation; never override the gate to reach Supervisor.
