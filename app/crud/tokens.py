from sqlalchemy.orm import Session
from datetime import datetime
from app.models.token import RevokedToken

def revoke_token(db: Session, jti: str, token_type: str, expires_at: datetime):
    if db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        return
    rec = RevokedToken(jti=jti, token_type=token_type, expires_at=expires_at)
    db.add(rec)
    db.commit()

def is_token_revoked(db: Session, jti: str) -> bool:
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None
