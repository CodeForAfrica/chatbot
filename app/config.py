"""Application settings, read from environment variables.

Every setting has a sensible default so the app runs with zero configuration.
Copy .env.example to .env (or export variables) to customise.
"""

import os


def _load_dotenv() -> None:
    """Best-effort loader for a local .env file (no external dependency).

    Only fills variables that aren't already set in the environment, so a
    real deployment secret always wins over the file. .env is gitignored and
    must never contain a committed key.
    """
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv()


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
# API key/token for the sensors.africa API, supplied via a deployment secret.
# NEVER commit the value — leave this empty in the repo and set it in the
# host's environment (Render env var, GitHub Actions secret, or local .env).
SENSORS_API_KEY = os.environ.get("SENSORS_API_KEY", "")
# Authorization header scheme. sensors.africa uses Django REST Framework token
# auth ("Authorization: Token <key>"). Set to "Bearer" for bearer tokens, or
# empty to send the raw key with no scheme prefix.
SENSORS_API_KEY_SCHEME = os.environ.get("SENSORS_API_KEY_SCHEME", "Token")
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
