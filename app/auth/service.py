from sqlalchemy.orm import Session
from models.permission import Permission
from models.user_role import UserRole
from models.role_permission import RolePermission

def get_user_permissions(user_id: int, db: Session) -> list[str]:
    rows = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]
