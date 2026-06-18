from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="bank-api",
            issuer="bank-auth"
        )
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permission(permission: str):
    def checker(user=Depends(get_current_user)):
        if permission not in user["perms"]:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return checker
