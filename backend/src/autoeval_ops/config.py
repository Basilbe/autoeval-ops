from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev"
    environment: str = "development"
    log_level: str = "DEBUG"
    max_concurrent_evals: int = 10
    eval_timeout_seconds: int = 300

    class Config:
        env_file = ".env"

settings = Settings()