from sqlalchemy.orm import Session
from app.models.post import Post as PostModel
from app.schemas.post import Post as PostSchema, PostOut, PostPatch


def create_post(db: Session, user_id: int, payload: PostSchema):
    post = PostModel(
        title=payload.title,
        content=payload.content,
        user_id=user_id
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def get_posts(db: Session):
    return db.query(PostModel).all()


def get_post(db: Session, post_id: int):
    return db.query(PostModel).filter(PostModel.id == post_id).first()


def update_post(db: Session, post_id: int, payload: PostPatch):
    post = get_post(db, post_id)
    if not post:
        return None
    if payload.title is not None:
        post.title = payload.title
    if payload.content is not None:
        post.content = payload.content
    db.commit()
    db.refresh(post)
    return post


def delete_post(db: Session, post_id: int):
    post = get_post(db, post_id)
    if not post:
        return None
    db.delete(post)
    db.commit()
    return post
