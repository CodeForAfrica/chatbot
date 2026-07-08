"""Lightweight intent + entity extraction for chat messages.

Rule-based on purpose: it is deterministic, free, works offline, and covers
the questions people actually ask an air-quality bot. Anything it cannot
classify falls through to the optional Claude layer (app/llm.py).
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Intent:
    name: str
    city: Optional[str] = None
    second_city: Optional[str] = None
    audience: str = "general"
    topic: Optional[str] = None
    extras: dict = field(default_factory=dict)


_GREETING = re.compile(
    r"^\s*(hi|hello|hey|hallo|habari|jambo|mambo|sasa|salut|bonjour|good\s*(morning|afternoon|evening)|start)\b",
    re.I,
)
_HELP = re.compile(r"\b(help|menu|options|what can you do|how do(es)? this work)\b", re.I)
_THANKS = re.compile(r"\b(thanks?|thank you|asante|merci|shukran)\b", re.I)
_COMPARE = re.compile(r"\b(compare|versus|vs\.?|difference between|worse than|better than|cleaner than)\b", re.I)
_WORST = re.compile(r"\b(worst|most polluted|dirtiest|highest pollution|highest pm)\b", re.I)
_BEST = re.compile(r"\b(best|cleanest|least polluted|lowest pollution|lowest pm)\b", re.I)
_TREND = re.compile(r"\b(trend|trending|improv|getting (better|worse)|chang(e|ing)|over time|history|past)\b", re.I)
_CITIES = re.compile(r"\b(which|what|list)\b.*\b(cities|city|places|locations)\b|\bcities\b\s*$", re.I)
_EXPLAIN = re.compile(r"\b(what is|what's|whats|explain|meaning of|define)\b", re.I)
_AIR = re.compile(r"\b(air|aqi|pollution|pm\s?2\.?5|pm\s?10|dust|smog|quality|breathe|breathing)\b", re.I)

_AUDIENCES = [
    ("children", re.compile(r"\b(child|children|kid|kids|school|baby|toddler|son|daughter)\b", re.I)),
    ("exercise", re.compile(r"\b(run|running|jog|jogging|exercise|workout|cycle|cycling|sport|training|gym)\b", re.I)),
    ("outdoor_workers", re.compile(r"\b(work outside|outdoor work|trader|market|vendor|boda|farmer|construction|hawker)\b", re.I)),
]

_HEALTH = re.compile(
    r"\b(safe|ok to|okay to|should i|can i|advice|health|mask|asthma|risk|danger|harmful)\b", re.I
)

_TOPICS = {
    "pm25": re.compile(r"pm\s?2\.?5", re.I),
    "pm10": re.compile(r"pm\s?10", re.I),
    "aqi": re.compile(r"\baqi\b|air quality index", re.I),
    "sensors": re.compile(r"\bsensor(s)?\b|sensors\.africa|network", re.I),
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def extract_cities(message: str, known_cities: list[str], limit: int = 2) -> list[str]:
    """Find known city names in a message, fuzzy-matched word by word."""
    normalized_msg = _normalize(message)
    found: list[tuple[int, str]] = []
    for city in known_cities:
        normalized_city = _normalize(city)
        idx = normalized_msg.find(normalized_city)
        if idx >= 0:
            found.append((idx, city))
    if not found:
        # Fuzzy pass for typos like "Nairbi" or "Laggos".
        words = re.findall(r"[a-z][a-z'\-]{3,}", normalized_msg)
        singles = {_normalize(c): c for c in known_cities if " " not in c}
        for pos, word in enumerate(words):
            matches = difflib.get_close_matches(word, singles.keys(), n=1, cutoff=0.84)
            if matches:
                found.append((pos, singles[matches[0]]))
    seen, ordered = set(), []
    for _, city in sorted(found):
        if city not in seen:
            seen.add(city)
            ordered.append(city)
    return ordered[:limit]


def parse(message: str, known_cities: list[str], last_city: Optional[str] = None) -> Intent:
    """Classify a message into an Intent, using last_city for follow-ups."""
    text = (message or "").strip()
    if not text:
        return Intent("help")

    cities = extract_cities(text, known_cities)
    city = cities[0] if cities else None
    second = cities[1] if len(cities) > 1 else None

    audience = "general"
    for name, pattern in _AUDIENCES:
        if pattern.search(text):
            audience = name
            break

    if _GREETING.search(text) and len(text) < 40 and not city:
        return Intent("greeting")
    if _HELP.search(text):
        return Intent("help")
    if _THANKS.search(text) and len(text) < 40:
        return Intent("thanks")
    if _COMPARE.search(text) and (second or (city and last_city and city != last_city)):
        return Intent("compare", city=city, second_city=second or last_city)
    if _WORST.search(text) and not city:
        return Intent("rank", extras={"order": "worst"})
    if _BEST.search(text) and not city:
        return Intent("rank", extras={"order": "best"})
    if _CITIES.search(text) and not city:
        return Intent("list_cities")

    effective_city = city or last_city
    if _TREND.search(text) and (effective_city or _AIR.search(text)):
        return Intent("trend", city=effective_city)
    if _HEALTH.search(text) and (effective_city or _AIR.search(text) or audience != "general"):
        return Intent("health", city=effective_city, audience=audience)
    if _EXPLAIN.search(text):
        for topic, pattern in _TOPICS.items():
            if pattern.search(text):
                return Intent("explain", topic=topic)
        if not city:
            return Intent("unknown")
    if city:
        return Intent("air_quality", city=city, audience=audience)
    if _AIR.search(text):
        if last_city:
            return Intent("air_quality", city=last_city, audience=audience)
        return Intent("ask_city")
    return Intent("unknown")
