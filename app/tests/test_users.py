# tests/test_posts.py
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.post import Post

def test_post_owner_or_admin_permissions(client, create_user, login_and_get_tokens):
    db: Session = SessionLocal()

    owner = create_user(db, email="owner@example.com", password="Passw0rd123", role="user")
    access_owner, _ = login_and_get_tokens("owner@example.com", "Passw0rd123")


    u2 = create_user(db, email="user2@example.com", password="Passw0rd123", role="user")
    access_u2, _ = login_and_get_tokens("user2@example.com", "Passw0rd123")


    admin = create_user(db, email="admin2@example.com", password="Passw0rd123", role="admin")
    access_admin, _ = login_and_get_tokens("admin2@example.com", "Passw0rd123")


    p = client.post("/posts", json={"title": "OwnerPost", "content": "zzz"}, headers={"Authorization": f"Bearer {access_owner}"})
    assert p.status_code == 201, p.text
    post_id = p.json()["id"]


    d1 = client.delete(f"/posts/{post_id}", headers={"Authorization": f"Bearer {access_u2}"})
    assert d1.status_code == 403


    d2 = client.delete(f"/posts/{post_id}", headers={"Authorization": f"Bearer {access_admin}"})
    assert d2.status_code in (204, 404)
