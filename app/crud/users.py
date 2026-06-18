from sqlalchemy.orm import Session
from app.models.user import User as UserModel
from app.schemas.user import UserCreate, UserUpdate
from app.auth.hashing import get_password_hash


def create_user(db: Session, user: UserCreate):
    db_user = UserModel(
        name=user.name,
        age=user.age,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_email(db: Session, email: str):
    return db.query(UserModel).filter(UserModel.email == email).first()


def get_users(db: Session):
    return db.query(UserModel).all()


def get_user(db: Session, user_id: int):
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def update_user(db: Session, user_id: int, payload: UserCreate):
    user = get_user(db, user_id)
    if not user:
        return None
    user.name = payload.name
    user.age = payload.age
    user.email = payload.email
    user.hashed_password = get_password_hash(payload.password)
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


def patch_user(db: Session, user_id: int, payload: UserUpdate):
    user = get_user(db, user_id)
    if not user:
        return None
    if payload.name is not None:
        user.name = payload.name
    if payload.age is not None:
        user.age = payload.age
    if payload.role is not None:
        user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    if not user:
        return None
    db.delete(user)
    db.commit()
    return True
