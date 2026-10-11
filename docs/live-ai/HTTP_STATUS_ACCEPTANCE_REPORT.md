# HTTP status evidence contract correction

Live-model tests for this change: **NOT RUN**. No paid requests were made.

## Root cause and minimal backend fix

`Finding.expected_value` previously allowed a string, integer, boolean or null without relating that type to `field`. Both specialist `Output` and `SupervisorOutput` use `Finding`. The strict provider schema inherited that union, so the Transaction model's `status_code` / `"504"` pair was schema-valid. Pydantic preserved the string. The evidence validator's exact typed comparison correctly found that string unequal to the cited integer 504; the defect was the output contract.

The provider now supplies two nested `anyOf` Finding variants: `status_code` requires an integer in the HTTP status range 100–599; other fields use the existing observation whitelist and exclude `status_code`. Both specialist and Supervisor outputs use this schema. Required properties and `additionalProperties: false` are preserved. The request-budget reservation includes the same expanded schema. Nested `anyOf` and integer limits are supported by the [OpenAI Structured Outputs schema subset](https://developers.openai.com/api/docs/guides/structured-outputs); actual live acceptance of the revised schema remains untested here.

The local Finding contract uses strict scalar types and one documented compatibility rule, `http-status-canonical-ascii-v1`: only an expected value for `field == "status_code"` comprising exactly three ASCII digits in the range `"100"`–`"599"` is converted to an integer. This handles historical and injected outputs. The original value/type and rule are recorded under the validated finding's `normalization` audit entry. Whitespace, signs, Unicode digits, leading zeros, decimals, scientific notation, booleans, nulls and out-of-range status values are rejected. Other fields receive no numeric conversion. Evidence payloads are never normalized.

Evidence ID membership, actual retrieval, matching source field, exact typed comparison against the source, context/snapshot and temporal restrictions remain enforced. Uncited claims remain insufficient. Contradictory source values remain contradicted. A supported predicate does not verify surrounding prose or a proposed causal explanation. No queue, action-authorization, execution, policy or frontend controls were weakened.

## Evaluation correction

The evaluation exports separate `SUPPORTED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE` and `NOT_EVALUATED` groups. Supported predicates alone undergo the accepted-predicate citation/source checks; a correctly rejected or uncited finding no longer falsely fails that check. Independent rechecks still catch false `SUPPORTED` labels. Accepted investigator results are distinguished from completed investigations.

Supervisor checks are **NOT RUN** only when accepted incomplete/escalated specialist results leave the native workflow awaiting human review without a Supervisor run. Missing Supervisor execution after completed specialists, empty investigations, and failed investigators remain failures. An incomplete workflow still has `automated_pass: false` and launcher exit code 1. No investigation is forced past human review.

## Saved live evidence, revalidated offline

The original `20261010T172115-live-79d708` artifact is unchanged. Its four historical requests are not new test executions. [Separate offline revalidation](artifacts/http-status-saved-evidence-revalidation/results.json) now has six supported predicates, zero contradicted predicates and three insufficient-evidence findings. Transaction's canonicalized 504 matches its cited integer source. Accepted predicates pass independent provenance and source-value rechecks. Supervisor checks are **NOT RUN** and the overall workflow remains incomplete. The three uncited claims and missing evidence still require human review.

## Verification

- Before the fix, the focused status regression suite reproduced failures: 16 failed, 8 passed; [JUnit](artifacts/http-status-before.xml).
- After the fix, 49 focused grounding, contract, runner and safety tests passed; [JUnit](artifacts/http-status-unit.xml).
- PostgreSQL phases 7–9 plus grounding/runner regressions: 109 passed; one existing transport test failed because its old assertion expected Finding properties directly instead of the new nested variants (229.63 seconds); [initial JUnit](artifacts/http-status-postgres.xml). The assertion now verifies required properties and forbidden additional properties in both variants, plus integer status type. Its isolated fresh-database rerun passed, 1/1; [rerun JUnit](artifacts/http-status-adapter.xml). No remaining failing test is known; the whole 110-test batch was not rerun after that assertion-only update.
- Fresh migration upgrade/downgrade/upgrade passed. All 54 frozen frontend files match their baseline hashes; the user's pre-existing frontend difference was preserved.

Coverage includes integer/string 504, invalid status forms/ranges, mismatched and wrongly typed evidence, absent source fields, unsupported claims, foreign/unretrieved citations, normalization audit, specialist/Supervisor schema shape, independently rejected false supported labels, human-review replay, queue fencing, preserved nonzero incomplete exit, and existing temporal/grounding safeguards.

## Local execution

From the ResolveOS directory, the unpaid rehearsal is `powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Offline`. Inspect the new directory's `REPORT.md` and `results.json`, especially finding groups, normalization, Supervisor check statuses and stop reason. Offline providers do not establish live-model quality. No production-readiness conclusion is made.
