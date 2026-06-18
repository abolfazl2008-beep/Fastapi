
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.user import User

def test_register_and_login_flow(client):

    reg = client.post("/auth/register", json={
        "name": "Ali",
        "age": 24,
        "email": "ali@example.com",
        "password": "Passw0rd123",
        "role": "user"
    })
    assert reg.status_code == 201, reg.text
    assert reg.json()["email"] == "ali@example.com"


    login = client.post("/auth/login", data={"username": "ali@example.com", "password": "Passw0rd123"})
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert "access_token" in tokens and "refresh_token" in tokens


    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/users", headers=headers)

    make_post = client.post("/posts", json={"title": "HelloWorld", "content": "fastapi!"}, headers=headers)
    assert make_post.status_code in (201, 401, 403)

def test_refresh_and_logout(client, create_user, login_and_get_tokens):

    db: Session = SessionLocal()
    u = create_user(db, email="bob@example.com", password="Passw0rd123", role="user")


    access, refresh = login_and_get_tokens("bob@example.com", "Passw0rd123")


    r = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    assert "access_token" in new_tokens and "refresh_token" in new_tokens


    headers = {"Authorization": f"Bearer {access}"}
    out = client.post("/auth/logout", headers=headers)
    assert out.status_code == 204


    check = client.post("/posts", json={"title": "abcde", "content": "x"}, headers=headers)
    assert check.status_code == 401
