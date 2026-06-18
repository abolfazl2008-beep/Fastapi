from datetime import timedelta
from core.security import create_jwt
from core.config import settings

def create_access_token(user_id: int, permissions: list[str], session_id: str):
    return create_jwt(
        {
            "sub": str(user_id),
            "sid": session_id,
            "perms": permissions
        },
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

def create_refresh_token(user_id: int):
    return create_jwt(
        {"sub": str(user_id)},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
