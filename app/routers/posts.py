# app/routers/posts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.schemas.post import Post as PostCreateSchema, PostOut, PostPatch
from app import crud
from app.auth.dependencies import get_current_user
from app.auth.permissions import require_owner_or_admin
from app.models import user as UserModel


router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("/", response_model=list[PostOut])
def list_posts(db: Session = Depends(get_db)):
    return crud.posts.get_posts(db)


@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    p = crud.posts.get_post(db, post_id)
    if not p:
        raise HTTPException(status_code=404, detail="Post not found")
    return p


@router.post("/", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return crud.posts.create_post(db, user_id=current_user.id, payload=payload)


@router.put("/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    payload: PostCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    p = crud.posts.get_post(db, post_id)
    if not p:
        raise HTTPException(status_code=404, detail="Post not found")

    require_owner_or_admin(current_user, resource_owner_id=p.user_id)

    updated = crud.posts.update_post(db, post_id, payload)

    if not updated:
        raise HTTPException(status_code=404, detail="Post not found")
    return updated


@router.patch("/{post_id}", response_model=PostOut)
def patch_post(
    post_id: int,
    payload: PostPatch,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    p = crud.posts.get_post(db, post_id)
    if not p:
        raise HTTPException(status_code=404, detail="Post not found")


    require_owner_or_admin(current_user, resource_owner_id=p.user_id)

    patched = crud.posts.patch_post(db, post_id, payload)
    if not patched:
        raise HTTPException(status_code=404, detail="Post not found")
    return patched


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    p = crud.posts.get_post(db, post_id)
    if not p:
        raise HTTPException(status_code=404, detail="Post not found")


    require_owner_or_admin(current_user, resource_owner_id=p.user_id)

    ok = crud.posts.delete_post(db, post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found")
    return None
