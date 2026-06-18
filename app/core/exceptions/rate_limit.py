from app.core.exceptions.base import AppBaseException


class RateLimitExceededError(AppBaseException):
    def __init__(
        self,
        message: str = "Too many requests",
        retry_after: int = 60,
        error_code: str = "RATE_LIMIT_EXCEEDED",
    ):
        super().__init__(
            status_code=429,
            message=message,
            error_code=error_code,
            extra={"retry_after": retry_after},
        )
