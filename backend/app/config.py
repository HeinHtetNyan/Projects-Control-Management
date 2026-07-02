from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/licensedb"
    JWT_SECRET: str = "dev-jwt-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    ENCRYPTION_KEY: str = ""
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"
    BASE_URL: str = "http://localhost:8001"
    APP_NAME: str = "Saw Yun License Server"
    CORS_ORIGINS: str = "http://localhost:3000"
    ENABLE_SCHEDULER: bool = True
    ROTATION_CHECK_INTERVAL_MINUTES: int = 1440

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
