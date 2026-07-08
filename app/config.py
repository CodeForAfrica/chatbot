"""Application settings, read from environment variables.

Every setting has a sensible default so the app runs with zero configuration.
Copy .env.example to .env (or export variables) to customise.
"""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# sensors.africa API
SENSORS_API_BASE = os.environ.get("SENSORS_API_BASE", "https://api.sensors.africa")
SENSORS_DATA_URL = os.environ.get("SENSORS_DATA_URL", f"{SENSORS_API_BASE}/v2/data/")
SENSORS_CITIES_URL = os.environ.get("SENSORS_CITIES_URL", f"{SENSORS_API_BASE}/v2/cities/")
# How many pages of /v2/data/ to walk per query (each page is ~100 records).
SENSORS_MAX_PAGES = _int("SENSORS_MAX_PAGES", 3)
SENSORS_TIMEOUT_SECONDS = _int("SENSORS_TIMEOUT_SECONDS", 20)
# Cache API responses for this long so a busy chatbot doesn't hammer the API.
CACHE_TTL_SECONDS = _int("CACHE_TTL_SECONDS", 300)

# Optional Claude integration for free-form questions.
# Leave ANTHROPIC_API_KEY unset to run fully rule-based (zero cost).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

# WhatsApp via Twilio (optional).
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

# WhatsApp via Meta Cloud API (optional).
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "sensors-africa-bot")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

# Chat sessions (web UI) are remembered for this long.
SESSION_TTL_SECONDS = _int("SESSION_TTL_SECONDS", 1800)
