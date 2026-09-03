"""Configuración de la API, leída del entorno.

Un único objeto `Settings` con validación en el arranque: si falta algo
imprescindible en producción el proceso no levanta, en lugar de fallar más
tarde en la primera petición que lo necesite.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: Environment = "development"

    # Postgres. La URL se compone aquí para no repetir credenciales en el
    # compose y en el entorno de la API.
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "futuro"
    postgres_user: str = "futuro"
    postgres_password: str = "futuro"

    # Sesión firmada. `httpOnly` + `SameSite=Lax`; `Secure` solo fuera de
    # desarrollo, porque en local se sirve por HTTP.
    session_secret: str = "dev-only-insecure-session-secret"
    session_cookie_name: str = "futuro_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14

    # OAuth de Google.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Allowlist de un solo email en la práctica, pero se acepta una lista
    # separada por comas para no tener que tocar código si algún día cambia.
    allowed_emails: str = ""

    # Solo se honra con env=development: inyecta un usuario fijo para
    # desarrollar sin depender de Google.
    dev_auth_bypass: bool = False
    dev_auth_email: str = "dev@localhost"

    # Origen público de la app, usado para construir el redirect de OAuth.
    public_base_url: str = "http://localhost:8080"

    log_level: str = Field(default="INFO")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_email_set(self) -> frozenset[str]:
        return frozenset(
            email.strip().lower()
            for email in self.allowed_emails.split(",")
            if email.strip()
        )

    @property
    def bypass_active(self) -> bool:
        """El bypass solo existe en desarrollo, nunca en producción."""
        return self.dev_auth_bypass and self.env == "development"

    @property
    def cookie_secure(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def check_production_requirements(self) -> Settings:
        if self.env != "production":
            return self
        missing = [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", self.google_client_id),
                ("GOOGLE_CLIENT_SECRET", self.google_client_secret),
                ("ALLOWED_EMAILS", self.allowed_emails),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "faltan variables obligatorias con ENV=production: "
                + ", ".join(missing)
            )
        if self.session_secret == Settings.model_fields["session_secret"].default:
            raise ValueError(
                "SESSION_SECRET no puede quedarse en el valor por defecto de "
                "desarrollo con ENV=production"
            )
        if not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL debe ser https:// con ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
