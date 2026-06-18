from fastapi import Request
from app.security.rate_limit import get_real_ip


def build_audit_meta(request: Request, extra: dict | None = None):
    return {
        "ip": get_real_ip(request),
        "user_agent": request.headers.get("user-agent"),
        **(extra or {}),
    }
