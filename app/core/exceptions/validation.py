from app.core.exceptions.base import AppBaseException


class ValidationError(AppBaseException):
    def __init__(
        self,
        message: str,
        field: str | None = None,
        error_code: str = "VALIDATION_ERROR",
    ):
        extra = {"field": field} if field else {}
        super().__init__(422, message, error_code, extra)
