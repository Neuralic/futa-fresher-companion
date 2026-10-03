from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "change-me-before-any-real-deployment"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    env: str = "development"
    database_url: str = "postgresql://futa:futa_dev_password@localhost:5432/futa"
    jwt_secret: str = _DEV_SECRET
    jwt_expires_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

if settings.env == "production" and settings.jwt_secret == _DEV_SECRET:
    raise RuntimeError("JWT_SECRET must be set to a strong secret in production")
