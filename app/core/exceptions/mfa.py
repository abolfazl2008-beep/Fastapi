
from app.core.exceptions.base import AppBaseException


class MFAVerificationError(AppBaseException):
    def __init__(self, message: str = "Invalid MFA code"):
        super().__init__(400, message, "MFA_INVALID_CODE")


class MFALockedError(AppBaseException):
    def __init__(self, message: str = "MFA is temporarily locked"):
        super().__init__(423, message, "MFA_LOCKED")


class MFANotConfiguredError(AppBaseException):
    def __init__(self, message: str = "MFA is not configured"):
        super().__init__(400, message, "MFA_NOT_CONFIGURED")
