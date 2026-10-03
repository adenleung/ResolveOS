from dataclasses import dataclass
from hmac import compare_digest

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Identity:
    user_id: str
    roles: frozenset[str]


def development_auth(settings):
    """Server-issued identity. Disabled by default and categorically unavailable in production."""
    def identify(authorization: str | None = Header(default=None)):
        if not settings.orchestration_dev_auth_enabled or settings.environment.lower() not in {"development", "test"}:
            raise HTTPException(503, "orchestration_auth_not_configured_for_this_environment")
        worker = settings.orchestration_dev_worker_token
        reviewer = settings.orchestration_dev_reviewer_token
        if not worker or not reviewer or len(worker.get_secret_value()) < 24 or len(reviewer.get_secret_value()) < 24:
            raise HTTPException(503, "development_auth_requires_distinct_long_tokens")
        if compare_digest(worker.get_secret_value().encode(), reviewer.get_secret_value().encode()):
            raise HTTPException(503, "development_auth_requires_distinct_long_tokens")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "orchestration_identity_required")
        token = authorization[7:]
        if compare_digest(token.encode(), worker.get_secret_value().encode()):
            return Identity("development-worker", frozenset({"WORKER"}))
        if compare_digest(token.encode(), reviewer.get_secret_value().encode()):
            return Identity(settings.orchestration_dev_reviewer_id, frozenset({"OPERATIONS_REVIEWER"}))
        raise HTTPException(401, "invalid_orchestration_identity")
    return identify
