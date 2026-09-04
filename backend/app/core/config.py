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
    DATABASE_URL: str = "postgresql+asyncpg://roadresq_user:roadresq_password@postgres:5432/roadresq_db"

    # Redis Cache & Presence Connection
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth & Security
    JWT_SECRET: str = "dev_jwt_secret_key_roadresq_2026_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
