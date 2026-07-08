# sensors.africa chatbot 🌍💬

**Converse with the air.** This is a mobile-friendly chatbot that turns the
massive, unstructured stream of readings from the
[sensors.africa](https://sensors.africa) network — low-cost air-quality
sensors across African cities — into plain-language answers anyone can act on.

A raw number means nothing to a parent walking a child to school, a market
trader planning their day, or a journalist writing a health story. This bot
closes that gap:

> **You:** Is it safe for my kids to walk to school in Lagos?
>
> **Bot:** 📍 Lagos: 🔴 AQI 152 — Unhealthy (PM2.5 54.9 µg/m³)
> 💡 Keep children indoors where possible; if they must be outside, keep it
> brief and avoid busy roads.

It runs as:

- a **mobile-first web chat** (the reusable link you deploy),
- a **WhatsApp chatbot** (Twilio *or* Meta Cloud API — pick either),
- a **JSON API** (`POST /api/chat`) you can embed anywhere.

## What it can answer

| You ask | It does |
|---|---|
| "Air quality in Nairobi" | Live AQI, PM2.5/PM10 means and ranges across all city sensors, WHO guideline comparison, health advice |
| "Is it safe for my kids to walk to school in Lagos?" | Audience-aware health guidance (children / runners / outdoor workers / general) |
| "Compare Nairobi and Kampala" | Side-by-side means with a plain-language verdict |
| "Which city is most polluted right now?" | Live worst/cleanest ranking across the network |
| "Is the air in Accra getting better?" | Short-window trend from timestamped readings |
| "What is PM2.5?" | Plain-language explainers for PM2.5, PM10, AQI, the network |
| Anything else | Optional Claude fallback, grounded in live computed stats (never fabricated numbers) |

All numbers come live from `https://api.sensors.africa/v2/data/` (cached for
5 minutes). The core bot is **fully rule-based and free to run** — no LLM key
required. Add an `ANTHROPIC_API_KEY` and free-form questions get answered by
Claude with the real sensor stats injected as context.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

Run the tests (fully offline — fixtures mimic the live API):

```bash
pip install -r requirements-dev.txt
pytest
```

## Deploy (get your reusable link)

**Render (one click):** connect this repo, choose "Blueprint", point at
`render.yaml`. Your bot lands at `https://<name>.onrender.com`.

**Docker (any host):**

```bash
docker build -t sensors-chatbot .
docker run -p 8000:8000 --env-file .env sensors-chatbot
```

**Railway / Fly.io / Heroku:** standard Python app; start command is
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## WhatsApp setup

### Option A — Twilio (fastest; sandbox works in minutes)

1. In the [Twilio Console](https://console.twilio.com), open
   **Messaging → Try it out → Send a WhatsApp message** (sandbox), or use a
   registered WhatsApp sender.
2. Set the inbound webhook ("When a message comes in") to
   `https://<your-deployment>/whatsapp/twilio` (HTTP POST).
3. Optionally set `TWILIO_AUTH_TOKEN` in your environment to enforce webhook
   signature verification.
4. Message the sandbox number: *"air quality in Nairobi"*.

### Option B — Meta WhatsApp Cloud API (direct, no middleman)

1. Create a Meta app with the WhatsApp product
   ([developers.facebook.com](https://developers.facebook.com)) and note the
   **access token** and **phone number ID**.
2. Set env vars: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and
   pick a `WHATSAPP_VERIFY_TOKEN` (any secret string).
3. In the app's WhatsApp → Configuration, set the webhook URL to
   `https://<your-deployment>/whatsapp/meta` with your verify token and
   subscribe to the `messages` field.
4. Message your WhatsApp business number.

Both channels share the same brain and per-user conversation memory ("air in
Nairobi" … "is it safe to run?" remembers Nairobi).

## Configuration

Copy `.env.example` to `.env`. Everything is optional; defaults run the bot
rule-based against the live sensors.africa API.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enable Claude for free-form questions (optional) |
| `ANTHROPIC_MODEL` | Model for the fallback (default `claude-opus-4-8`) |
| `SENSORS_MAX_PAGES` | Pages of the data API to walk per query (default 3) |
| `CACHE_TTL_SECONDS` | API response cache lifetime (default 300) |
| `TWILIO_AUTH_TOKEN` | Verify Twilio webhook signatures |
| `WHATSAPP_*` | Meta Cloud API credentials (see above) |

## Architecture

```
message ─→ nlu.py (intent + city extraction, fuzzy typo matching)
             │
             ▼
        responder.py ──→ sensors_client.py ──→ api.sensors.africa (cached)
             │                 │
             │                 ▼
             │            insights.py (means, medians, trends, rankings)
             │                 │
             │                 ▼
             │            aqi.py (EPA AQI, WHO guidelines, health advice)
             │
             ├─→ known intent → templated plain-text answer (free, instant)
             └─→ free-form + ANTHROPIC_API_KEY → llm.py (Claude, grounded in
                 computed stats — never invents numbers)

channels: web chat (/) · JSON API (/api/chat) · WhatsApp (Twilio + Meta)
```

- **`app/aqi.py`** — pure conversion of µg/m³ → AQI/category/emoji, WHO 2021
  guideline comparisons, audience-specific advice. Zero dependencies.
- **`app/sensors_client.py`** — async client for `/v2/data/` with pagination,
  defensive parsing (bad timestamps, garbage/sentinel values, missing
  locations) and a TTL cache.
- **`app/insights.py`** — pure statistics: city summaries, worst/cleanest
  rankings, short-window trends.
- **`app/nlu.py`** — deterministic intent parser; fuzzy city matching handles
  typos ("Nairbi" → Nairobi) and accents.
- **`app/responder.py`** — orchestrates everything; per-session memory for
  follow-up questions.
- **`app/llm.py`** — optional Claude integration (facts-first: we compute,
  it phrases).
- **`app/whatsapp.py` + `app/main.py`** — channel adapters and FastAPI wiring.

## Data source & credits

Data: [sensors.africa](https://sensors.africa) — a citizen-science air
quality network by [Code for Africa](https://codeforafrica.org).
AQI breakpoints: US EPA (2024 PM2.5 revision). Health guidance thresholds:
WHO Global Air Quality Guidelines (2021).
