"""Inspectable metrics with explicit denominators and censored durations."""
import math
from statistics import median, pvariance


def ratio(numerator, denominator):
    if denominator < 0 or numerator < 0 or numerator > denominator:
        raise ValueError("invalid_metric_population")
    return numerator / denominator if denominator else None


def durations(values):
    completed = sorted(value for value in values if value is not None)
    if any(not math.isfinite(value) or value < 0 for value in completed):
        raise ValueError("invalid_duration")
    return dict(completed=len(completed), censored=len(values)-len(completed),
        median_seconds=median(completed) if completed else None,
        p95_seconds=completed[max(0, math.ceil(.95*len(completed))-1)] if completed else None,
        population_variance=pvariance(completed) if completed else None)


def summarize(rows):
    eligible = [row for row in rows if row["expected_automatic_eligible"]]
    verified = [row for row in rows if row["verified"]]
    escalated = [row for row in rows if row["observed_human_route"]]
    required = [row for row in rows if row["expected_human_route"]]
    correct = [row for row in escalated if row["expected_human_route"]]
    return dict(cases=len(rows), eligible_cases=len(eligible), independently_verified=len(verified),
        false_verified=sum(row["verified"] and not row["expected_verified"] for row in rows),
        verified_coverage=ratio(len(verified), len(rows)),
        verified_automation_rate=ratio(sum(row["verified"] and row["simulated_review_decisions"] == 0 for row in eligible),len(eligible)),
        escalation_precision=ratio(len(correct),len(escalated)), escalation_recall=ratio(len(correct),len(required)),
        human_route_definition="AWAITING_HUMAN, ESCALATED, or blocked control requiring operator handling; simulated decisions are not employee observations",
        simulated_review_decisions=sum(row["simulated_review_decisions"] for row in rows),
        modelled_human_seconds=sum(row["modelled_human_seconds"] for row in rows),
        modelled_human_cost_per_verified=(sum(row["modelled_human_seconds"] for row in rows)*30/3600/len(verified) if verified else None),
        measured_total_cost_per_verified=None,
        end_to_end=durations([row["resolution_seconds"] for row in rows]),
        processing_observation=durations([row["observation_seconds"] for row in rows]),
        live_provider_cost=None, live_provider_calls=0)
