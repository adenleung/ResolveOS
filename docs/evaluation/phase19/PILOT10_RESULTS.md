# Ten-case pilot results
LIVE MODEL TESTS: **NOT RUN**. Zero paid requests. Both final CLI tracks returned 0 and all ten cases completed their track-specific evaluation.

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

[Native offline results](artifacts/20261011T044418-offline-d5f38f/results.json) and [rules results](artifacts/20261011T044418-rules-f894fa/results.json).

```json
{
  "cases_selected": 10,
  "cases_evaluated": 10,
  "detection_accuracy": {
    "numerator": 10,
    "denominator": 10,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "classification_accuracy": {
    "numerator": 10,
    "denominator": 10,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "routing_accuracy": {
    "numerator": 10,
    "denominator": 10,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "completion_decision_accuracy": {
    "numerator": 10,
    "denominator": 10,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "escalation_precision": {
    "numerator": 5,
    "denominator": 5,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "escalation_recall": {
    "numerator": 5,
    "denominator": 5,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "unnecessary_escalation_candidate_rate": {
    "numerator": 0,
    "denominator": 4,
    "value": 0.0,
    "status": "COMPLETED"
  },
  "unsafe_completion_candidate_rate": {
    "numerator": 0,
    "denominator": 5,
    "value": 0.0,
    "status": "COMPLETED"
  },
  "supervisor_participation": {
    "numerator": 4,
    "denominator": 4,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "narrative_quality": "PENDING REVIEW",
  "critical_failures": 0,
  "live_reasoning_accuracy": "NOT RUN",
  "denominators": "Decision metrics exclude NOT RUN/FAILED/INCOMPLETE and retain an explicit incomplete count; never treat missing results as successes.",
  "incomplete_cases": 0,
  "grounding_precision": {
    "numerator": 158,
    "denominator": 158,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "required_fact_coverage": {
    "numerator": 56,
    "denominator": 56,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "source_retrieval_coverage": {
    "numerator": 56,
    "denominator": 56,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "citation_validity": {
    "numerator": 158,
    "denominator": 158,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "temporal_source_validity": {
    "numerator": 158,
    "denominator": 158,
    "value": 1.0,
    "status": "COMPLETED"
  },
  "by_family": {
    "financial-disagreement": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "ESCALATE"
      ]
    },
    "source-conflict": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "ESCALATE"
      ]
    },
    "retry-lifecycle": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "COMPLETE"
      ]
    },
    "stale-workflow": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "NO_EXCEPTION"
      ]
    },
    "policy-restricted": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "ESCALATE"
      ]
    },
    "missing-authority": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "ESCALATE"
      ]
    },
    "api-degradation": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "COMPLETE"
      ]
    },
    "late-ledger-correction": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "COMPLETE"
      ]
    },
    "duplicate-risk": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "ESCALATE"
      ]
    },
    "delayed-ack": {
      "cases": 1,
      "statuses": [
        "COMPLETED"
      ],
      "decisions": [
        "COMPLETE"
      ]
    }
  },
  "unsupported_accepted_predicates": 0
}
```

These are deterministic fixture expectations. No real-model operational accuracy is measured. Each case exports raw persisted native results, task/tool telemetry, preregistered truth, source identities, frozen hashes and a manual review packet. Actual billed cost is unobserved; offline tokens and fixture latency are not GPT telemetry. All per-case databases were dropped.

Actual persisted specialist runs by role: {'TECHNOLOGY': 5, 'TRANSACTION': 7, 'RISK': 3}. Tool statuses: {'AVAILABLE': 15, 'UNAVAILABLE': 3}. UNAVAILABLE denotes the explicitly absent policy-applicability connector, not fabricated evidence or a provider transport failure. Supervisor ran four times; all usage here is deterministic.
