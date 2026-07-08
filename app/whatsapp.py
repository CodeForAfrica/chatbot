"""WhatsApp channel adapters.

Two ways to run the bot on WhatsApp — both hit the same Responder:

1. Twilio WhatsApp (quickest to set up, works with the Twilio sandbox):
   point the sandbox/number webhook at POST /whatsapp/twilio. Twilio sends
   form-encoded fields (Body, From) and expects TwiML XML back.

2. Meta WhatsApp Cloud API (direct, no middleman):
   point the app webhook at /whatsapp/meta. GET handles Meta's one-time
   verification handshake; POST receives message events and we reply via
   the Graph API using WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID.
"""

import base64
import hashlib
import hmac
import logging
from xml.sax.saxutils import escape

import httpx

from . import config

logger = logging.getLogger(__name__)

# WhatsApp caps messages at 4096 chars; stay well under it.
MAX_MESSAGE_CHARS = 3500


def clip(text: str) -> str:
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return text[: MAX_MESSAGE_CHARS - 1] + "…"


# --- Twilio -----------------------------------------------------------------

def twiml_response(text: str) -> str:
    """Wrap a reply in TwiML for Twilio's webhook response."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{escape(clip(text))}</Message></Response>"
    )


def verify_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """Validate X-Twilio-Signature (only enforced when TWILIO_AUTH_TOKEN is set).

    Twilio's scheme: append sorted POST params to the full URL, HMAC-SHA1
    with the auth token, base64-encode.
    """
    if not config.TWILIO_AUTH_TOKEN:
        return True  # verification disabled
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(
        config.TWILIO_AUTH_TOKEN.encode(), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")


# --- Meta WhatsApp Cloud API --------------------------------------------------

def extract_meta_messages(payload: dict) -> list[dict]:
    """Pull inbound text messages out of a Meta webhook payload.

    Returns [{"from": wa_id, "text": body}] — ignores statuses/reactions/media.
    """
    messages = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                if msg.get("type") == "text":
                    body = (msg.get("text") or {}).get("body", "").strip()
                    sender = msg.get("from", "")
                    if body and sender:
                        messages.append({"from": sender, "text": body})
    return messages


async def send_meta_message(to: str, text: str) -> bool:
    """Send a reply through the Graph API."""
    if not (config.WHATSAPP_ACCESS_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID):
        logger.warning("Meta WhatsApp reply skipped: credentials not configured")
        return False
    url = f"https://graph.facebook.com/v20.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": clip(text)},
    }
    headers = {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=body, headers=headers, timeout=15)
            response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Meta WhatsApp send failed: %s", exc)
        return False
