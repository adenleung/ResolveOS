# Risk/control matrix

| Threat / actor opportunity | Entry | Control | Test evidence | Residual limitation | Owner |
|---|---|---|---|---|---|
| Prompt injection / misleading summary | Permitted source text or reviewed memory | Read-only role tools; sanitized payloads; NOT_EVALUATED authority; independent controls | Phase 7/11, hardening grounding and AI contracts | Real-model adversarial robustness unmeasured | AI/backend |
| False citation / absent predicate | Specialist and Supervisor output | Reference scope and explicit field-presence/type equality | Grounding before/after and Phase 7/8 | Narrative meaning is unverified | AI/backend |
| Stale worker / duplicate effect | Durable worker retries | Database claim locks, lease token, post-effect fence and unique logical effect | Phase 6/10 concurrent/process tests | Production distributed failover untested | SRE |
| Stale/revoked approval or policy | Action submission/execution | Action binding, expiry, current fingerprint and role check | Phase 9/10; stale-policy headless | Enterprise identity/tenant adapter absent | Controls |
| False verification | Source state after effect | Independent reread including protected ledger balance | New balance regression, Phase 10, failure headless | Finite tested synthetic field scope | Backend |
| Replay identity content conflict | Ingestion retry | Immutable original, persisted conflict, atomic exact-retry counters | Hardening concurrent and conflicting replay tests | Source authenticity not cryptographically established | Data/backend |
| Memory contamination / future availability | Reviewed retrieval | Verified source chain, publication integrity, grants, withdrawal and snapshot cutoff | Phase 11 and temporal hardening tests | Small ranking experiment; no historical policy reconstruction guarantee | Memory |
| Hidden label leakage | Simulator/evaluation tools | Explicit source columns/payload allowlist; evaluator labels isolated | Phase 7/15 and AI sanitization | No live-model leakage study | Evaluation |
| Synthetic source mutation / setup authenticity | Public simulator/ingestion/correlation routes in app/main.py | Synthetic-only scope; operational effects still require protected current controls | Foundation/Phase 2–5 and control regressions | Source/setup APIs are not enterprise-authenticated; local trusted prototype only; ORM startup create_all remains a deployment concern | Security/backend |
| Credential misuse | Dev auth / provider setup | Distinct long tokens, production denial, SecretStr, disabled live inference | Config/Phase 6/15; runtime manifest | No enterprise identity or external penetration test | Security |

All controls are prototype assertions evidenced by finite tests. Residual risks remain visible; ownership labels are proposed engineering roles, not employee assignments. See the threat model for current MAS source/date applicability and limitations.
