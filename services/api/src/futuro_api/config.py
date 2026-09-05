"""Configuración de la API, leída del entorno.

Un único objeto `Settings` con validación en el arranque: si falta algo
imprescindible en producción el proceso no levanta, en lugar de fallar más
tarde en la primera petición que lo necesite.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from futuro_api.llm import cost

Environment = Literal["development", "production"]
LlmProvider = Literal["openai", "stub"]


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

    # Cola de trabajos. Vacía significa «sin cola»: la aplicación levanta
    # igual y solo falla lo que necesita encolar. En producción es
    # obligatoria.
    redis_url: str = "redis://redis:6379/0"

    # Repositorio de datos privado, de solo lectura. Es de donde salen el
    # modelo de scoring, la guía de variantes de CV y los PDF que se
    # descargan: sin él no se puntúa ni se sirve ningún CV, pero todo lo
    # demás funciona.
    #
    # Vacío significa «no hay repositorio de datos». Hasta M2 no era
    # obligatorio con `ENV=production` porque el clon de solo lectura no
    # existía todavía y negarse a arrancar habría tumbado la aplicación
    # entera por una función que no podía funcionar. M3 trae el clon, así
    # que pasa a la lista de obligatorias de abajo: en producción ya no hay
    # motivo para arrancar sin él.
    data_repo_path: str = ""

    # LLM. El valor por defecto es `stub` porque es el que hace que el
    # harness y el e2e funcionen sin clave y sin gastar: el CI no tiene
    # credenciales de OpenAI y no debería tenerlas. Que ese sea el valor por
    # defecto no es un riesgo de producción, porque `ENV=production` lo
    # rechaza igual que rechaza el bypass de autenticación.
    llm_provider: LlmProvider = "stub"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_timeout_seconds: float = 120.0

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
    def data_repo_root(self) -> Path | None:
        """La raíz del repositorio de datos, o `None` si no hay ninguno."""
        return Path(self.data_repo_path) if self.data_repo_path else None

    @property
    def llm_stubbed(self) -> bool:
        """El cliente simulado solo existe fuera de producción."""
        return self.llm_provider == "stub" and self.env != "production"

    @property
    def bypass_active(self) -> bool:
        """El bypass solo existe en desarrollo, nunca en producción."""
        return self.dev_auth_bypass and self.env == "development"

    @property
    def cookie_secure(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def check_llm_requirements(self) -> Settings:
        """Con `openai`, la clave y el modelo son obligatorios ya.

        Y el modelo tiene que tener tarifa conocida: preferimos no arrancar
        antes que registrar un coste que nadie sabe calcular. Falla en el
        arranque y no en el primer trabajo encolado, que es donde el error
        saldría en un log del worker y no en la cara de quien despliega.
        """
        if self.llm_provider != "openai":
            return self
        missing = [
            name
            for name, value in (
                ("OPENAI_API_KEY", self.openai_api_key),
                ("OPENAI_MODEL", self.openai_model),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "faltan variables obligatorias con LLM_PROVIDER=openai: "
                + ", ".join(missing)
            )
        if not cost.is_priced(self.openai_model):
            raise ValueError(str(cost.UnknownModel(self.openai_model)))
        return self

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
                ("REDIS_URL", self.redis_url),
                ("DATA_REPO_PATH", self.data_repo_path),
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
        if self.llm_provider != "openai":
            raise ValueError(
                "LLM_PROVIDER=stub no vale con ENV=production: las "
                "extracciones serían simuladas y nada lo delataría en la "
                "interfaz salvo el nombre del modelo"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
