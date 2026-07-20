from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment variables (see .env.example).
    Every Railway service that imports this (backend, cron) needs the same
    DATABASE_URL and SECRET_KEY; only the backend web service needs the
    frontend/CORS and VAPID settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Sessions
    secret_key: str
    session_max_age_days: int = 365

    # CORS — the deployed frontend's origin, e.g. https://tada-frontend.up.railway.app
    frontend_url: str = "http://localhost:3000"

    # Web Push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_email: str = "info@endurance-decking.com"


settings = Settings()
