
from fastapi import HTTPException
from typing import Any, Dict, Optional


class AppBaseException(HTTPException):
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.error_code = error_code or f"ERR_{status_code}"
        self.extra = extra or {}
        super().__init__(
            status_code=status_code,
            detail={
                "message": message,
                "error_code": self.error_code,
                **self.extra,
            },
        )
