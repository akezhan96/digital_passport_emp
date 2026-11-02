"""Deployment boundary. Production data never participates in development tools."""
import os

PRODUCTION = os.getenv("APP_ENV", "development") == "production"


def require_development():
    if PRODUCTION:
        raise RuntimeError("Операция доступна только на тестовом стенде / "
                           "Әрекет тек сынақ ортасында қолжетімді")
