
from enum import Enum


class RoleEnum(str, Enum):
    ADMIN = "admin"
    USER = "user"
    ORG_USER = "org_user"
