"""FastAPI app: mobile web chat + JSON API + WhatsApp webhooks.

Routes:
  GET  /                 mobile-friendly chat UI
  POST /api/chat         {"message": "...", "session_id": "..."} → {"reply": "..."}
  GET  /api/cities       cities the bot knows about
  GET  /whatsapp/meta    Meta Cloud API verification handshake
  POST /whatsapp/meta    Meta Cloud API inbound messages
  POST /whatsapp/twilio  Twilio WhatsApp webhook (TwiML response)
  GET  /health           liveness probe
"""

import logging
import pathlib

from fastapi import BackgroundTasks, FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import config, whatsapp
from .responder import Responder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="sensors.africa chatbot",
    description="Converse with live air-quality data from African cities.",
    version="0.1.0",
)

responder = Responder()

_STATIC = pathlib.Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(default="web", max_length=128)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_enabled": bool(config.ANTHROPIC_API_KEY)}


@app.post("/api/chat")
async def chat(body: ChatRequest) -> dict:
    reply = await responder.reply(body.message, session_id=body.session_id)
    return {"reply": reply}


@app.get("/api/cities")
async def cities() -> dict:
    return {"cities": await responder.client.list_cities()}


# --- WhatsApp: Meta Cloud API -------------------------------------------------

@app.get("/whatsapp/meta")
async def meta_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return JSONResponse({"error": "verification failed"}, status_code=403)


@app.post("/whatsapp/meta")
async def meta_webhook(request: Request, background: BackgroundTasks) -> dict:
    try:
        payload = await request.json()
    except ValueError:
        return {"status": "ignored"}
    for message in whatsapp.extract_meta_messages(payload):
        background.add_task(_answer_meta, message["from"], message["text"])
    # Always 200 quickly so Meta doesn't retry/disable the webhook.
    return {"status": "received"}


async def _answer_meta(sender: str, text: str) -> None:
    reply = await responder.reply(text, session_id=f"wa:{sender}")
    await whatsapp.send_meta_message(sender, reply)


# --- WhatsApp: Twilio ----------------------------------------------------------

@app.post("/whatsapp/twilio")
async def twilio_webhook(request: Request) -> Response:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    signature = request.headers.get("X-Twilio-Signature", "")
    if not whatsapp.verify_twilio_signature(str(request.url), params, signature):
        return Response(status_code=403)
    body = params.get("Body", "").strip()
    sender = params.get("From", "twilio")
    reply = await responder.reply(body, session_id=f"wa:{sender}") if body else (
        "Send me a message like \"air quality in Nairobi\"."
    )
    return Response(content=whatsapp.twiml_response(reply), media_type="application/xml")
