import pyotp
from typing import Tuple
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.redis_service import RedisService
from app.core.logging import logger
from app.core.exceptions.mfa import MFANotConfiguredError, MFALockedError, MFAInvalidCodeError


def verify_mfa(
    *,
    db: Session,
    user: User,
    code: str,
    ip: str,
    user_agent: str,
    fingerprint: str,
    valid_window: int = 2,
    mark_used: bool = True,
    fail_lock_threshold: int = 5,
    redis: RedisService,
) -> Tuple[bool, int, bool, int]:

    if not user.mfa_enabled or not user.mfa_secret:
        raise MFANotConfiguredError()

    totp = pyotp.TOTP(user.mfa_secret, digits=6, interval=30)
    if not totp.verify(code, valid_window=valid_window):

        fail_key = f"mfa:fail:{user.id}"
        fail_count = redis.incr(fail_key)
        redis.expire(fail_key, 3600)


        fp_set_key = f"mfa:fp_set:{user.id}"
        redis.sadd(fp_set_key, fingerprint)
        redis.expire(fp_set_key, 900)
        if redis.scard(fp_set_key) > 3:
            raise MFALockedError(extra={"retry_after": 1800})

        if fail_count >= fail_lock_threshold:
            return False, 900, True, fail_count

        return False, 0, False, fail_count


    redis.delete(f"mfa:fail:{user.id}")
    redis.delete(f"mfa:fp_fail:{fingerprint}")
    redis.delete(f"mfa:fp_set:{user.id}")

    if mark_used:
        invalidate_old_tokens(user=user, db=db, redis=redis, ip=ip, user_agent=user_agent, fingerprint=fingerprint)

    return True, 0, False, 0


def invalidate_old_tokens(
    *,
    user: User,
    db: Session,
    redis: RedisService,
    ip: str,
    user_agent: str,
    fingerprint: str,
):
    try:
        # 1. Redis sessions / refresh / MFA tokens
        redis.delete_pattern(f"rt:*{user.id}*")
        redis.delete_pattern(f"session:{user.id}:*")
        redis.delete_pattern(f"mfa:session:{user.id}:*")

        # 2. DB refresh tokens (اگر دارید)
        # db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})

        # 3. blacklist fingerprint for 24h
        redis.set_key(f"mfa:blacklist_fp:{fingerprint}", "1", expire=86400 * 7)

        logger.info("OLD_TOKENS_INVALIDATED", extra={"user_id": user.id, "ip": ip})
    except Exception as e:
        logger.error("INVALIDATE_TOKENS_FAILED", exc_info=True, extra={"user_id": user.id})
