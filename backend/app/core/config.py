import os
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    # Override in .env with a strong random value (>= 32 bytes required for HMAC-SHA256)
    SECRET_KEY: str = "change-me-in-production-use-a-random-64-char-hex-string-here!!"

    _DEFAULT_SECRET: str = "change-me-in-production-use-a-random-64-char-hex-string-here!!"

    @model_validator(mode="after")
    def _reject_default_secret(self) -> "Settings":
        if self.SECRET_KEY == self._DEFAULT_SECRET:
            raise ValueError(
                "SECRET_KEY is still the insecure default. "
                "Set a strong random value in your .env file."
            )
        return self
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/naturalsk.db"
    UPLOAD_DIR: str = "./uploads"
    DATA_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    AVATARS_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "avatars"))
    FILE_TTL_HOURS: int = 6
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
