# Memory Option B experiment

`py -3.13 run_memory_evaluation.py` builds four actual independently verified, reviewed PostgreSQL histories and 12 correlated retrieval queries. One history has stale policy; one is withdrawn. No revoked history is returned. Current eligibility/role/case/source/verified-source/content integrity checks occur before either algorithm's ranking. Temporal tests additionally exclude reviews after the investigator snapshot and reject naive/future cutoffs.

| Algorithm | Precision@1 | Precision@3 | Recall@3 (positive queries) | MRR | nDCG@3 (positive queries) |
|---|---|---|---|---|---|
| overlap-recency-1.0 | 0.0 | 0.2222 | 1.0 | 0.2778 | 0.5655 |
| structured-policy-2.0 | 0.6667 | 0.2222 | 1.0 | 0.6667 | 1.0 |

Relevance is explicitly current-policy guidance with matching observed endpoint. No subjective root-cause accuracy is inferred. Precision@3 uses denominator 3, even when fewer results exist; recall/nDCG omit no-relevant queries as undefined and MRR includes them as zero. Byte usage and measured per-query latency are in artifacts/memory-evaluation.json. Both algorithms still return same-category irrelevant histories on no-match queries, and identical Precision@3/Recall@3 show the limit of this ordering experiment.

Option B `structured-policy-2.0`: current policy +100, shared permitted source system +2 each, exact endpoint +20/mismatch -20, error type +30/mismatch -30, service name +5/mismatch -5, status code +5/mismatch -5; missing features contribute zero. Stable recency breaks equal-score ties within the existing 50-candidate window. Category, review, withdrawal, permissions and integrity remain hard filters. The score is neither confidence nor cause. Only approved observed payload fields are used; summaries and hidden labels are excluded. Contributions are inspectable in returned similarity metadata and ranking version is audited in retrieval limits. Rollback is choosing the original `overlap-recency-1.0`.

Decision: retain the original operational default. Option B is explicitly selectable by trusted Python callers for further evaluation; APIs and investigator runtime defaults do not change. Sample size and repeated templates cannot establish significance or investigation/time benefit. Broad older-case recall, root-cause discrimination, robust business-process taxonomy and production retrieval load remain unverified. No pgvector, graph database, autonomous memory learning or extra agent was added.
