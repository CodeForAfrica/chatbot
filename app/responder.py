"""Orchestrator: message in → natural-language answer out.

Flow: parse intent → fetch live readings → compute stats → render a plain-
text reply that reads well in WhatsApp and the web chat. Free-form questions
fall through to the optional Claude layer with computed stats as context.
"""

import asyncio
import logging
import time
from typing import Optional

from . import config, llm
from .aqi import AqiResult, combined_aqi, health_advice, who_comparison
from .insights import compute_trend, rank_cities, summarize_city
from .nlu import Intent, parse
from .sensors_client import SensorsClient

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "I turn live air-quality data from sensors.africa into plain answers. Try:\n"
    "• \"Air quality in Nairobi\"\n"
    "• \"Is it safe for my kids to walk to school in Lagos?\"\n"
    "• \"Compare Nairobi and Kampala\"\n"
    "• \"Which city is most polluted right now?\"\n"
    "• \"Is the air in Accra getting better?\"\n"
    "• \"What is PM2.5?\"\n"
    "• \"List cities\""
)

GREETING_TEXT = (
    "👋 Hello! I'm the sensors.africa air-quality bot. Ask me about the air in "
    "your city — for example \"How is the air in Nairobi?\" or \"Is it safe to "
    "run in Lagos today?\" Send \"help\" for more examples."
)

EXPLAINERS = {
    "pm25": (
        "PM2.5 is fine dust smaller than 2.5 micrometres — about 30× thinner than "
        "a human hair. It comes from traffic, cooking fires, dust and burning "
        "waste, and it's the most dangerous common pollutant because it goes deep "
        "into the lungs and bloodstream. The WHO says 24-hour average exposure "
        "should stay under 15 µg/m³. Ask me for a city to see live PM2.5 levels."
    ),
    "pm10": (
        "PM10 is inhalable dust smaller than 10 micrometres — think road dust, "
        "construction and smoke. It irritates the nose, throat and lungs. The WHO "
        "guideline is a 24-hour average under 45 µg/m³. Ask me for a city to see "
        "live PM10 levels."
    ),
    "aqi": (
        "The Air Quality Index turns pollution measurements into one 0–500 score: "
        "🟢 0–50 good, 🟡 51–100 moderate, 🟠 101–150 unhealthy for sensitive "
        "groups, 🔴 151–200 unhealthy, 🟣 201–300 very unhealthy, 🟤 301+ "
        "hazardous. I calculate it from live PM2.5 and PM10 sensor readings."
    ),
    "sensors": (
        "sensors.africa is a citizen-science network of low-cost air-quality "
        "sensors across African cities, run by Code for Africa. The sensors "
        "report dust levels (PM2.5 and PM10) every few minutes, and I read that "
        "live feed to answer your questions. Data: api.sensors.africa"
    ),
}


class _Sessions:
    """Tiny in-memory conversation memory (last city per session)."""

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._store: dict = {}

    def get(self, session_id: str) -> dict:
        entry = self._store.get(session_id)
        if entry and time.monotonic() - entry[0] < self.ttl:
            return entry[1]
        return {}

    def update(self, session_id: str, **kwargs):
        state = self.get(session_id)
        state.update(kwargs)
        self._store[session_id] = (time.monotonic(), state)
        if len(self._store) > 10000:  # bound memory
            oldest = sorted(self._store.items(), key=lambda kv: kv[1][0])[:5000]
            for key, _ in oldest:
                self._store.pop(key, None)


def _fmt_aqi_line(result: AqiResult) -> str:
    return f"{result.emoji} AQI {result.aqi} — {result.category}"


def _freshness(summary) -> str:
    if not summary.latest:
        return ""
    return f" (latest reading {summary.latest.strftime('%d %b %H:%M')} UTC)"


class Responder:
    def __init__(self, client: Optional[SensorsClient] = None):
        self.client = client or SensorsClient()
        self.sessions = _Sessions(config.SESSION_TTL_SECONDS)

    async def reply(self, message: str, session_id: str = "web") -> str:
        state = self.sessions.get(session_id)
        known_cities = await self.client.list_cities()
        intent = parse(message, known_cities, last_city=state.get("last_city"))

        if intent.city:
            self.sessions.update(session_id, last_city=intent.city)

        handler = getattr(self, f"_handle_{intent.name}", None)
        if handler is None:
            return HELP_TEXT
        try:
            return await handler(intent, message)
        except Exception:  # never let one bad query kill the webhook
            logger.exception("handler for intent %s failed", intent.name)
            return ("Sorry, something went wrong fetching the data. "
                    "Please try again in a moment.")

    # --- intent handlers -------------------------------------------------

    async def _handle_greeting(self, intent: Intent, message: str) -> str:
        return GREETING_TEXT

    async def _handle_help(self, intent: Intent, message: str) -> str:
        return HELP_TEXT

    async def _handle_thanks(self, intent: Intent, message: str) -> str:
        return "You're welcome! Breathe easy 🌍 Ask me anytime."

    async def _handle_ask_city(self, intent: Intent, message: str) -> str:
        return ("Which city are you asking about? For example: "
                "\"air quality in Nairobi\". Send \"list cities\" to see "
                "where we have sensors.")

    async def _handle_explain(self, intent: Intent, message: str) -> str:
        return EXPLAINERS.get(intent.topic or "", HELP_TEXT)

    async def _handle_list_cities(self, intent: Intent, message: str) -> str:
        readings = await self.client.fetch_readings()
        live = sorted({r.city.strip().title() for r in readings if r.city.strip()})
        if live:
            shown = ", ".join(live[:25])
            return (f"Cities reporting data right now: {shown}."
                    "\nAsk me about any of them, e.g. \"air in "
                    f"{live[0]}\".")
        cities = await self.client.list_cities()
        return ("Cities in the sensors.africa network include: "
                + ", ".join(cities[:25])
                + ". Ask me about any of them.")

    async def _handle_air_quality(self, intent: Intent, message: str) -> str:
        assert intent.city
        summary, aqi_result = await self._city_snapshot(intent.city)
        if summary is None or summary.reading_count == 0:
            return self._no_data(intent.city)
        lines = [f"📍 {summary.city or intent.city}{_freshness(summary)}"]
        if aqi_result:
            lines.append(_fmt_aqi_line(aqi_result))
        if summary.pm25_mean is not None:
            lines.append(f"PM2.5: {summary.pm25_mean} µg/m³ "
                         f"(range {summary.pm25_min}–{summary.pm25_max} across "
                         f"{summary.sensor_count} sensor location(s))")
        if summary.pm10_mean is not None:
            lines.append(f"PM10: {summary.pm10_mean} µg/m³")
        who = who_comparison(summary.pm25_mean, summary.pm10_mean)
        if who:
            lines.append(who)
        if aqi_result:
            lines.append("💡 " + health_advice(aqi_result, intent.audience))
        return "\n".join(lines)

    async def _handle_health(self, intent: Intent, message: str) -> str:
        if not intent.city:
            return await self._handle_ask_city(intent, message)
        summary, aqi_result = await self._city_snapshot(intent.city)
        if summary is None or aqi_result is None:
            return self._no_data(intent.city)
        advice = health_advice(aqi_result, intent.audience)
        return (f"📍 {summary.city or intent.city}: {_fmt_aqi_line(aqi_result)} "
                f"(PM2.5 {summary.pm25_mean} µg/m³)\n💡 {advice}")

    async def _handle_trend(self, intent: Intent, message: str) -> str:
        if not intent.city:
            return await self._handle_ask_city(intent, message)
        readings = await self.client.fetch_readings(city=intent.city)
        trend = compute_trend(readings)
        if trend is None:
            return (f"I don't have enough timestamped readings from "
                    f"{intent.city} right now to compute a trend. "
                    "Try asking for the current air quality instead.")
        arrow = {"rising": "📈 worsening", "falling": "📉 improving", "steady": "➡️ steady"}[trend.direction]
        return (f"PM2.5 in {intent.city} is {arrow} over the most recent "
                f"readings: {trend.earlier_mean} → {trend.later_mean} µg/m³ "
                f"({trend.change_percent:+.0f}%, based on {trend.reading_count} "
                "readings). Note this reflects the latest data window, not a "
                "long-term climate trend.")

    async def _handle_compare(self, intent: Intent, message: str) -> str:
        if not (intent.city and intent.second_city):
            return ("Tell me two cities to compare, e.g. "
                    "\"compare Nairobi and Lagos\".")
        sum_a, aqi_a = await self._city_snapshot(intent.city)
        sum_b, aqi_b = await self._city_snapshot(intent.second_city)
        if not sum_a or sum_a.reading_count == 0:
            return self._no_data(intent.city)
        if not sum_b or sum_b.reading_count == 0:
            return self._no_data(intent.second_city)
        lines = ["⚖️ Air quality comparison (mean PM2.5):"]
        for summary, aqi_result in ((sum_a, aqi_a), (sum_b, aqi_b)):
            emoji = aqi_result.emoji if aqi_result else "•"
            aqi_txt = f"AQI {aqi_result.aqi}" if aqi_result else "AQI n/a"
            lines.append(f"{emoji} {summary.city}: {summary.pm25_mean} µg/m³ ({aqi_txt})")
        if sum_a.pm25_mean is not None and sum_b.pm25_mean is not None:
            if abs(sum_a.pm25_mean - sum_b.pm25_mean) < 2:
                verdict = "Both cities currently have similar air."
            else:
                cleaner = sum_a if sum_a.pm25_mean < sum_b.pm25_mean else sum_b
                dirtier = sum_b if cleaner is sum_a else sum_a
                ratio = dirtier.pm25_mean / cleaner.pm25_mean if cleaner.pm25_mean else 0
                verdict = (f"{cleaner.city} currently has cleaner air"
                           + (f" — about {ratio:.1f}× lower PM2.5." if ratio else "."))
            lines.append(verdict)
        return "\n".join(lines)

    async def _handle_rank(self, intent: Intent, message: str) -> str:
        readings = await self.client.fetch_readings()
        ranked = rank_cities(readings)
        if not ranked:
            return ("I couldn't rank cities right now — the live feed didn't "
                    "return enough city-tagged readings. Try asking about a "
                    "specific city instead.")
        order = intent.extras.get("order", "worst")
        top = ranked[:5] if order == "worst" else list(reversed(ranked))[:5]
        title = ("😷 Most polluted cities right now (mean PM2.5):" if order == "worst"
                 else "🌿 Cleanest cities right now (mean PM2.5):")
        lines = [title]
        for i, (city, value, count) in enumerate(top, 1):
            aqi_result = combined_aqi(value, None)
            emoji = aqi_result.emoji if aqi_result else "•"
            lines.append(f"{i}. {emoji} {city}: {value} µg/m³")
        lines.append("Based on the latest readings from the sensors.africa network.")
        return "\n".join(lines)

    async def _handle_unknown(self, intent: Intent, message: str) -> str:
        if llm.available():
            context = await self._llm_context(message)
            answer = await asyncio.to_thread(llm.answer, message, context)
            if answer:
                return answer
        return ("I'm not sure how to answer that one.\n\n" + HELP_TEXT)

    # --- helpers ----------------------------------------------------------

    async def _city_snapshot(self, city: str):
        readings = await self.client.fetch_readings(city=city)
        if not readings:
            return None, None
        summary = summarize_city(readings, city)
        aqi_result = combined_aqi(summary.pm25_mean, summary.pm10_mean)
        return summary, aqi_result

    def _no_data(self, city: str) -> str:
        return (f"I couldn't find recent readings for {city}. The sensors "
                "there may be offline. Send \"list cities\" to see where "
                "data is coming in right now.")

    async def _llm_context(self, message: str) -> str:
        """Compute a compact stats block for the Claude layer."""
        known_cities = await self.client.list_cities()
        from .nlu import extract_cities

        cities = extract_cities(message, known_cities) or []
        parts = []
        for city in cities[:2]:
            summary, aqi_result = await self._city_snapshot(city)
            if summary and summary.reading_count:
                parts.append(
                    f"{summary.city or city}: mean PM2.5 {summary.pm25_mean} µg/m³, "
                    f"mean PM10 {summary.pm10_mean} µg/m³, "
                    f"{summary.reading_count} readings from "
                    f"{summary.sensor_count} locations"
                    + (f", AQI {aqi_result.aqi} ({aqi_result.category})" if aqi_result else "")
                )
        if not parts:
            readings = await self.client.fetch_readings()
            ranked = rank_cities(readings)[:8]
            if ranked:
                parts.append("Current mean PM2.5 by city: "
                             + "; ".join(f"{c} {v} µg/m³" for c, v, _ in ranked))
        return "\n".join(parts)
