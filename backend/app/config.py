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

    # Enchanted Spoon shopping-list push (SPEC §6 Supplies). Enchanted
    # Spoon is the recipe app formerly named MealGenie — these fields keep
    # the old name so deployed env vars keep working. Base URL of its API
    # (no trailing slash) and the shared first-party API key — the SAME
    # value as INTEGRATION_API_KEY on the enchanted-spoon Railway backend
    # service. Leave empty to disable the integration (supplies still
    # track status locally).
    mealgenie_api_url: str = ""
    mealgenie_api_key: str = ""

    # In-app feedback -> a GitHub issue on the Tada repo (services/
    # github_service.py). A fine-grained PAT with Issues: write on that
    # repo, and "owner/repo". Leave both empty to disable in local dev —
    # submissions still return a response, just without a real issue.
    github_token: str = ""
    github_repo: str = ""

    # Hearth integration (docs/hearth-integration.md): the static device
    # token the Hearth wall presents as `Authorization: Bearer <token>`
    # on the /api/hearth router. It authorizes the DEVICE, not a user —
    # the acting household member rides in each request body/query. It
    # must EQUAL the TADA_DEVICE_TOKEN env var on Hearth's Railway
    # service. Leave empty to disable the integration entirely (every
    # /api/hearth route then returns 503). Needed by the "backend"
    # service only.
    hearth_device_token: str = ""


settings = Settings()
