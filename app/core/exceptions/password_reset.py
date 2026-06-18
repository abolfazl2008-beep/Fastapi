from app.core.exceptions.base import AppBaseException


class ResetTokenInvalid(AppBaseException):
    def __init__(self, message: str = "Invalid or expired reset token"):
        super().__init__(400, message, "RESET_TOKEN_INVALID")


class ResetTokenMismatchError(AppBaseException):
    def __init__(self, message: str = "Reset token context mismatch (IP/Device)"):
        super().__init__(400, message, "RESET_TOKEN_MISMATCH")


class PasswordResetNotAllowedError(AppBaseException):
    def __init__(self, message: str = "Password reset is not allowed for this account"):
        super().__init__(403, message, "RESET_NOT_ALLOWED")


class PasswordTooWeakError(AppBaseException):
    def __init__(self, message: str = "Password does not meet security requirements"):
        super().__init__(422, message, "PASSWORD_TOO_WEAK")