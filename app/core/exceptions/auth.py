
from app.core.exceptions.base import AppBaseException

class InvalidTokenError(AppBaseException):
    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(401, message, "AUTH_INVALID_TOKEN")


class MissingTokenError(AppBaseException):
    def __init__(self, message: str = "Authorization token is missing"):
        super().__init__(401, message, "AUTH_MISSING_TOKEN")


class InsufficientPermissionsError(AppBaseException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(403, message, "AUTH_FORBIDDEN")


class UserInactiveError(AppBaseException):
    def __init__(self, message: str = "User account is inactive"):
        super().__init__(403, message, "AUTH_USER_INACTIVE")


class UserLockedError(AppBaseException):
    def __init__(self, message: str = "User account is locked"):
        super().__init__(403, message, "AUTH_USER_LOCKED")