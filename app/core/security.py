from __future__ import annotations
import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import jwt, JWTError, ExpiredSignatureError, InvalidAudienceError, InvalidIssuerError
from app.core.config import settings


pwd_context = CryptContext(schemes=["argon2"],deprecated="auto",)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def _load_key(value: str, *, is_path: bool = False) -> str:
    if is_path:
        if not os.path.exists(value):
            raise FileNotFoundError(f"JWT key file not found: {value}")
        try:
            with open(value, "r", encoding="utf-8") as f:
                return f.read().strip()
        except PermissionError:
            raise PermissionError(f"No permission to read JWT key file: {value}")
    return value.strip()


PRIVATE_KEY = _load_key(
    settings.JWT_PRIVATE_KEY,
    is_path=settings.JWT_PRIVATE_KEY_IS_PATH,
)
PUBLIC_KEY = _load_key(
    settings.JWT_PUBLIC_KEY,
    is_path=settings.JWT_PUBLIC_KEY_IS_PATH,
)
JWT_ALGORITHM = settings.JWT_ALGORITHM



def _now() -> datetime:
    return datetime.now(timezone.utc)

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: int,
    role: str,
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    now = _now()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm=JWT_ALGORITHM,
        headers={"typ": "JWT", "alg": JWT_ALGORITHM},
    )


def create_refresh_token(*,user_id: int,expires_delta: timedelta = timedelta(days=7),) -> tuple[str, str]:
    now = _now()
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": jti,
    }
    raw_token = jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm=JWT_ALGORITHM,
        headers={"typ": "JWT", "alg": JWT_ALGORITHM},
    )
    return raw_token, jti


def verify_access_token(token: str) -> Dict[str, Any]:

    try:
        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": True,
                "require": ["exp", "iat", "iss", "aud", "sub", "jti"],
            },
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        return payload
    except ExpiredSignatureError:
        raise JWTError("Token has expired")
    except InvalidAudienceError:
        raise JWTError("Invalid audience")
    except InvalidIssuerError:
        raise JWTError("Invalid issuer")
    except JWTError as e:
        raise JWTError(f"Invalid token: {str(e)}")


def verify_refresh_token(token: str) -> Dict[str, Any]:
    return verify_access_token(token)
