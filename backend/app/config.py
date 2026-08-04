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

    # MealGenie shopping-list push (SPEC §6 Supplies). Base URL of the
    # MealGenie API (no trailing slash) and the shared first-party API key —
    # the SAME key set on the MealGenie Railway service. Leave empty to
    # disable the integration (supplies still track status locally).
    mealgenie_api_url: str = ""
    mealgenie_api_key: str = ""

    # In-app feedback -> a GitHub issue on the Tada repo (services/
    # github_service.py). A fine-grained PAT with Issues: write on that
    # repo, and "owner/repo". Leave both empty to disable in local dev —
    # submissions still return a response, just without a real issue.
    github_token: str = ""
    github_repo: str = ""


settings = Settings()
