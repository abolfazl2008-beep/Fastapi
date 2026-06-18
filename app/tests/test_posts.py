
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.user import User

def test_users_list_requires_admin(client, create_user, login_and_get_tokens):
    db: Session = SessionLocal()


    user = create_user(db, email="u1@example.com", password="Passw0rd123", role="user")
    access_u, _ = login_and_get_tokens("u1@example.com", "Passw0rd123")


    admin = create_user(db, email="admin@example.com", password="Passw0rd123", role="admin")
    access_a, _ = login_and_get_tokens("admin@example.com", "Passw0rd123")


    r1 = client.get("/users", headers={"Authorization": f"Bearer {access_u}"})
    assert r1.status_code == 403


    r2 = client.get("/users", headers={"Authorization": f"Bearer {access_a}"})
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)
