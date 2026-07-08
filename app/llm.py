"""Optional Claude integration for free-form questions.

The rule-based responder handles the common questions at zero cost. When a
message falls outside those patterns AND an ANTHROPIC_API_KEY is configured,
we ask Claude — but facts-first: we compute the numbers from live sensor
data ourselves and inject them as context, so the model phrases answers
around real measurements instead of inventing them.

Without a key this module reports unavailable and the bot degrades
gracefully to a help message.
"""

import logging
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the sensors.africa air-quality assistant, answering \
questions from people across African cities on WhatsApp and a mobile web chat.

Rules:
- Ground every factual claim in the sensor data provided in the context block. \
If the context has no data for the question, say so plainly and suggest asking \
about a city in the network.
- Audience: parents, traders, runners, journalists — not scientists. Explain \
numbers in plain language and say what they mean for daily life.
- Keep replies short (under 120 words), plain text only — no markdown, no \
tables. Emoji are fine sparingly.
- Concentrations are in µg/m³. PM2.5 is fine particulate matter (the most \
health-relevant); the WHO 24-hour guideline is 15 µg/m³ for PM2.5 and \
45 µg/m³ for PM10.
- Never fabricate readings, cities, or trends."""


def available() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def answer(question: str, data_context: str) -> Optional[str]:
    """Ask Claude to answer `question` grounded in `data_context`.

    Returns the reply text, or None on any failure (caller falls back).
    """
    if not available():
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; skipping LLM answer")
        return None

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Live sensor data context (computed from api.sensors.africa):\n"
                        f"{data_context or 'No live data was available for this query.'}\n\n"
                        f"Question: {question}"
                    ),
                }
            ],
        )
    except anthropic.APIConnectionError:
        logger.warning("Claude request failed: network error")
        return None
    except anthropic.RateLimitError:
        logger.warning("Claude request failed: rate limited")
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Claude request failed: %s %s", exc.status_code, exc.message)
        return None

    if response.stop_reason == "refusal":
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or None
