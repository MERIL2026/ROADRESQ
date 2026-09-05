from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "RoadResQ Backend API"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # PostgreSQL + PostGIS Connection
    POSTGRES_USER: str = "roadresq_user"
    POSTGRES_PASSWORD: str = "roadresq_password"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "roadresq_db"
    DATABASE_URL: str = (
        "postgresql+asyncpg://roadresq_user:roadresq_password@postgres:5432/roadresq_db"
    )

    # Redis Cache & Presence Connection
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth & Security
    JWT_SECRET: str = "dev_jwt_secret_key_roadresq_2026_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OTP Settings
    OTP_LENGTH: int = 6
    OTP_EXPIRE_SECONDS: int = 300  # 5 minutes
    OTP_RESEND_COOLDOWN_SECONDS: int = 60  # 1 minute
    OTP_MAX_ATTEMPTS: int = 3

    # Rate Limiting
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 900  # 15 minutes
    RATE_LIMIT_OTP_MAX_REQUESTS: int = 5
    RATE_LIMIT_OTP_WINDOW_SECONDS: int = 3600  # 1 hour
    RATE_LIMIT_REFRESH_MAX_REQUESTS: int = 20
    RATE_LIMIT_REFRESH_WINDOW_SECONDS: int = 60  # 1 minute

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

