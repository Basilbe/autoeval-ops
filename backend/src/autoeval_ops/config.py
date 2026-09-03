from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at backend/src/autoeval_ops/config.py — four levels below
# the repo root. Resolve .env from an absolute path so it loads correctly
# regardless of the working directory the process is launched from.
_REPO_ROOT = Path(__file__).resolve().parents[3]

def resolve_repo_path(path: str) -> Path:
    """Resolve a path from .env relative to the repo root, regardless of
    the working directory the process was launched from."""
    p = Path(path)
    return p if p.is_absolute() else _REPO_ROOT / p

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev"

    # Server
    environment: str = "development"
    log_level: str = "DEBUG"

    # Evaluation
    max_concurrent_evals: int = 10
    eval_timeout_seconds: int = 300

    # GitHub App (Phase 2)
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    github_webhook_secret: str = ""

    # Clerk (Phase 3; live verification deferred to Phase 4)
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""

    # Observability (Phase 5)
    otel_enabled: bool = True
    otel_exporter_endpoint: str = "http://localhost:4318"

    @property
    def async_database_url(self) -> str:
        """Managed Postgres providers hand out postgresql:// URLs, which
        route SQLAlchemy to the sync psycopg2 driver. This project uses
        asyncpg. Normalizing here means the deployment platform's value
        can be used verbatim without hand-editing."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        extra="ignore",
    )


settings = Settings()