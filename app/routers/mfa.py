from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from celery.result import AsyncResult
from app.core.redis_service import get_redis_service, RedisService
from app.core.auth import get_current_user
from app.core.rate_limit import limiter, mfa_rate_limit_key
from app.core.security import safe_hash
from app.core.ip import get_real_ip
from app.schemas.mfa import MFAVerifyRequest, MFAVerifyResponse
from app.tasks.mfa_tasks import mfa_verify_task
from app.core.config import settings

router = APIRouter(prefix="/mfa", tags=["MFA"])

def build_fingerprint(ip: str, ua: str) -> str:
    return safe_hash(f"{ip}:{ua}")

@router.post("/verify", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("15/5minutes;60/hour", key_func=mfa_rate_limit_key)
async def verify_mfa_endpoint(
    request: Request,
    payload: MFAVerifyRequest,
    redis: RedisService = Depends(get_redis_service),
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    headers = {"Cache-Control": "no-store"}

    if not idempotency_key:
        raise HTTPException(400, "Missing X-Idempotency-Key", headers=headers)

    if not user:
        raise HTTPException(401, "Unauthorized", headers=headers)

    ip = get_real_ip(request)
    ua = (request.headers.get("user-agent") or "unknown")[:200]
    fingerprint = build_fingerprint(ip, ua)

    # idempotency
    idem_key = f"mfa:idem:{user.id}:{idempotency_key}"
    was_set = await redis.set_key(idem_key, "processing", nx=True, expire=300)
    if not was_set:
        status_val = await redis.get_key(idem_key)
        raise HTTPException(
            429,
            f"Duplicate request (status={status_val})",
            headers={"Retry-After": "5", **headers},
        )

    # fingerprint brute-force protection
    fp_key = f"mfa:fp_fail:{fingerprint}"
    fp_fails = await redis.increment(fp_key, expire=900)
    if fp_fails > settings.MFA_FINGERPRINT_MAX_FAILS:
        raise HTTPException(
            429,
            "Too many attempts from this device",
            headers={"Retry-After": "300", **headers},
        )

    job = mfa_verify_task.delay(
        user_id=user.id,
        code=payload.code,
        ip=ip,
        ua=ua,
        fingerprint=fingerprint,
        idem_key=idem_key,
    )

    return {
        "status": "ACCEPTED",
        "task_id": job.id,
        "message": "MFA verification in progress",
    }


@router.get("/verify/status/{task_id}")
async def mfa_verify_status(task_id: str):
    result = AsyncResult(task_id)
    if result.state == "PENDING":
        return {"status": "PENDING"}
    if result.state == "SUCCESS":
        return {"status": result.result.get("status")}
    if result.state == "FAILURE":
        return {"status": "FAILURE"}
    return {"status": result.state}
