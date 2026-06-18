
from app.core.exceptions.base import AppBaseException


class EmailServiceUnavailableError(AppBaseException):
    def __init__(self, message: str = "Email service is temporarily unavailable"):
        super().__init__(503, message, "EMAIL_SERVICE_DOWN")


class InvalidRecipientError(AppBaseException):
    def __init__(self, message: str = "Invalid or disallowed recipient email"):
        super().__init__(400, message, "EMAIL_INVALID_RECIPIENT")

class EmailRateLimitError(AppBaseException):
    def __init__(self, message: str = "Email sending rate limit reached"):
        super().__init__(429, message, "EMAIL_RATE_LIMIT")

