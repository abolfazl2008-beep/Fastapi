from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr
from pathlib import Path
from datetime import timedelta


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    SECRET_KEY: str = "super-secret-123-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "RS256"
    PRIVATE_KEY: str = ""
    PUBLIC_KEY: str = ""
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:6555/Test"
    SMTP_HOST: str = "smtp.yourbankmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "no-reply@yourbank.com"
    SMTP_PASSWORD: str = "STRONG_PASSWORD"
    SMTP_FROM: EmailStr = "no-reply@yourbank.com"
    SMTP_TLS: bool = True
    EMAIL_VERIFY_EXP_MIN: int = 2
    MAX_ATTEMPTS: int = 5
    LOCK_MINUTES: int = 15
    COOLDOWN_MINUTES: int = 3
    VERIFICATION_COOLDOWN_MINUTES: int = 5
    MFA_FAILED_MESSAGE: str = "The verification was unsuccessful. Please try again."
    MFA_LOCKED_MESSAGE: str = "Too many attempts. Please try again later."
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB_RATE_LIMIT: int = 1
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False
    RATE_LIMIT_SALT: str = "super-secret-123"
    KEY_VERSION: str = "v2"
    VERSION: str = "v1"
    CORS_ALLOWED_ORIGINS: str = "https://bank-ui.com"
    ADMIN_DAILY_EMAIL_LIMIT: int = 100
    MAX_METADATA_KEYS: int = 20
    MAX_METADATA_VALUE_LENGTH: int = 500
    MAX_USER_AGENT_LENGTH: int = 300
    EMAIL_TOKEN_PURPOSE: str = "verify_email"
    LOGIN_LIMIT: int = 5
    LOGIN_WINDOW: int = 300
    REFRESH_LIMIT: int = 10
    REFRESH_WINDOW: int = 600
    ACCOUNT_LOCK_TIME: int = 900
    CELERY_BROKER_URL: str = "redis://localhost:6379/5"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/6"
    PASSWORD_RESET_DB_TIMEOUT_SECONDS:int
    MAX_DLQ_LENGTH:int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()


