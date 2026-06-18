# app/tests/conftest.py
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app
from app.database.base import Base
from app.database.session import get_db
import app.database.session as db_session_module  # مهم: برای پچ کردن engine/SessionLocal
from app.models.user import User
from app.auth.hashing import get_password_hash

# --- یک SQLite in-memory مشترک بین همه کانکشن‌ها
TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,            # نکتهٔ حیاتی
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


db_session_module.engine = engine
db_session_module.SessionLocal = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db() -> Generator:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def create_user():
    def _create(
        db,
        *,
        name="Test User",
        age=25,
        email="user@example.com",
        password="Passw0rd123",
        role="user",
    ):
        u = User(
            name=name,
            age=age,
            email=email,
            hashed_password=get_password_hash(password),
            role=role.upper() if isinstance(role, str) else role,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    return _create


@pytest.fixture
def login_and_get_tokens(client):
    def _login(email: str, password: str):
        r = client.post("/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        data = r.json()
        # با توجه به خروجی خودت اگر کلیدها فرق دارند، تطبیق بده
        return data.get("access_token"), data.get("refresh_token")
    return _login
