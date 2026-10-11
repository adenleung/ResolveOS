# Controlled real-model handoff
No paid calls were authorized or made. Use the existing local environment; no key argument/file or secret inspection is needed. Native model profile is explicitly selected via --model gpt-4.1-mini-2025-04-14. Only this reviewed profile is accepted; another model needs independently reviewed schema/pricing support. Per-case model/limits are supported via --case-config JSON keyed by selected IDs. A case configuration cannot add cases or exceed previous caps.

From ResolveOS with existing DATABASE_URL and backend Python dependencies:

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track offline --output docs/evaluation/phase20/artifacts/LOCAL-offline
py -3.13 -m scripts.run_evaluation_benchmark --track rules --output docs/evaluation/phase20/artifacts/LOCAL-rules
py -3.13 -m scripts.evaluate_quality integrity --input docs/evaluation/phase20/artifacts/LOCAL-offline
py -3.13 -m scripts.evaluate_quality suite --input docs/evaluation/phase20/artifacts/LOCAL-offline --output docs/evaluation/phase20/artifacts/LOCAL-scorecard
```

All output paths must be NEW; choose a different suffix on each invocation. One explicitly authorized paid development case (NOT RUN here):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-07 --model gpt-4.1-mini-2025-04-14 --authorize-paid-cases 1 --case-max-seconds 600 --batch-max-seconds 900 --batch-max-requests 10 --batch-max-tokens 120000 --batch-max-usd 0.15
```

Separately explicitly authorized two-case development batch (NOT RUN here):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-07 P19-02 --authorize-paid-cases 2 --case-max-seconds 600 --batch-max-seconds 1800 --batch-max-requests 20 --batch-max-tokens 240000 --batch-max-usd 0.30
```

Only selected cases execute. Default remains unpaid. Native metering still wraps the real provider directly, so missing usage retains reservations and halts; deadline fencing sits outside it. No automatic retry/fallback. Runtime checks occur before requests and task stages; native socket timeout is shortened to the remaining deadline. These are cooperative investigation deadlines, not hard process kills: migrations, socket I/O edge conditions and DB cleanup may extend wall time. Ctrl+C preserves partial records and drops the owned DB via finally; the safety guard stops unrun cases. Critical safety failures, uncertain billed usage, batch budget/deadline or interruption stop further work. Per-case limits remain 10 requests,120000 accounted tokens, USD0.15 estimate,3 specialist turns,12 tools,2048 output tokens/request.

P19-07 separates slow/failed API advisory assessment from definitive cause; P19-02 tests genuinely absent authoritative receipt. Together they test completion and escalation, not an attempt to make Scenario C reach Supervisor. A meaningful improvement is source retrieval and independently reviewed proportionate decisions with uncertainty preserved, not higher completion counts. Expected outputs include native tasks/results, actual role requests, usage, frozen prompt/evaluator/configuration hashes, quality layers and review packets. Estimated caps are not actual bills. Inspect REPORT.md/results.json/quality-evaluation.json and run the quality suite command. Any quality judgement requires separate expert review.
