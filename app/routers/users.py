from fastapi import APIRouter, Depends, status, Request
from app.core.dependencies import get_current_user, require_admin
from app.schemas.user import UserOut, AdminUserOut
from app.core.rate_limit import limiter

router = APIRouter(prefix="/users", tags=["Users"])


def per_user_key(request: Request):
    user = request.state.user
    return f"user:{user.id}"


@router.get("/me",response_model=UserOut,status_code=status.HTTP_200_OK)
@limiter.limit("30/minute", key_func=per_user_key)
async def get_current_user_profile(current_user=Depends(get_current_user)):
    return current_user


@router.get("/admin",response_model=AdminUserOut,status_code=status.HTTP_200_OK,)
async def admin_check(admin_user=Depends(require_admin)):
    return admin_user


@router.get("/admin/dashboard",response_model=dict,status_code=status.HTTP_200_OK)
async def admin_dashboard(admin_user=Depends(require_admin)):
    return {"message": "Welcome to Admin Dashboard","admin_id": admin_user.id,"role": "admin"}

