"""Experimental Option B: exact structured similarity, never causal confidence."""
BASELINE = "overlap-recency-1.0"
OPTION_B = "structured-policy-2.0"
FEATURES = {"endpoint": 20, "error_type": 30, "service_name": 5, "status_code": 5}


def signatures(payloads):
    return {field: {str(payload[field]) for payload in payloads if field in payload and payload[field] is not None}
        for field in FEATURES}


def contributions(current_policy, source_overlap, current, historical):
    result = {"current_policy": 100 if current_policy else 0, "source_overlap": 2*source_overlap}
    for field, weight in FEATURES.items():
        left, right = current.get(field,set()), historical.get(field,set())
        result[field] = weight if left and right and left.intersection(right) else -weight if left and right else 0
    return result
