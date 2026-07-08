"""Client for the sensors.africa open data API.

The primary endpoint is https://api.sensors.africa/v2/data/?city=&country=&type=
which returns paginated sensor records. Each record looks roughly like:

    {
      "id": 123,
      "timestamp": "2026-07-08T10:00:00Z",
      "location": {"latitude": "-1.28", "longitude": "36.82",
                   "country": "KE", "city": "Nairobi"},
      "sensor": {"id": 2, "sensor_type": {"name": "SDS011"}},
      "sensordatavalues": [
        {"value": "12.5", "value_type": "P2"},   # PM2.5
        {"value": "20.1", "value_type": "P1"}    # PM10
      ]
    }

Parsing is deliberately defensive: fields may be missing, values may be
strings, and the envelope may be either a paginated object or a bare list.
Responses are cached in memory for CACHE_TTL_SECONDS.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from . import config

logger = logging.getLogger(__name__)

# Cities with sensors.africa deployments — used to seed city recognition
# even when the live /v2/cities/ endpoint is unreachable.
KNOWN_CITIES = [
    "Nairobi", "Lagos", "Dar es Salaam", "Accra", "Kampala", "Addis Ababa",
    "Johannesburg", "Cape Town", "Durban", "Pretoria", "Abuja", "Port Harcourt",
    "Mombasa", "Kisumu", "Nakuru", "Dodoma", "Arusha", "Mwanza", "Bamako",
    "Yaoundé", "Douala", "Kinshasa", "Lubumbashi", "Abidjan", "Dakar",
    "Ouagadougou", "Lomé", "Cotonou", "Kigali", "Bujumbura", "Lusaka",
    "Harare", "Gaborone", "Windhoek", "Maputo", "Antananarivo", "Port Louis",
    "Cairo", "Alexandria", "Tunis", "Algiers", "Casablanca", "Monrovia",
    "Freetown", "Banjul", "Niamey", "N'Djamena", "Juba", "Khartoum", "Asmara",
    "Djibouti", "Mogadishu", "Lilongwe", "Blantyre", "Beira", "Stone Town",
]


@dataclass
class Reading:
    """One sensor record, flattened."""
    city: str = ""
    country: str = ""
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sensor_type: str = ""
    values: dict = field(default_factory=dict)  # e.g. {"P2": 12.5, "P1": 20.1}

    @property
    def pm25(self) -> Optional[float]:
        return self.values.get("P2")

    @property
    def pm10(self) -> Optional[float]:
        return self.values.get("P1")


def _plain_float(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _to_float(value) -> Optional[float]:
    f = _plain_float(value)
    # The network occasionally reports sentinel/garbage measurement values.
    if f is None or f < 0 or f > 5000:
        return None
    return f


def _parse_timestamp(value) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def parse_record(record: dict) -> Optional[Reading]:
    """Flatten one raw API record into a Reading. Returns None if unusable."""
    if not isinstance(record, dict):
        return None
    location = record.get("location") or {}
    sensor = record.get("sensor") or {}
    sensor_type = (sensor.get("sensor_type") or {}).get("name", "") if isinstance(sensor, dict) else ""

    values: dict = {}
    for datum in record.get("sensordatavalues") or []:
        if not isinstance(datum, dict):
            continue
        vtype = datum.get("value_type")
        val = _to_float(datum.get("value"))
        if vtype and val is not None:
            values[str(vtype)] = val

    # Some deployments expose averaged records with top-level P1/P2 keys.
    for key in ("P0", "P1", "P2", "humidity", "temperature"):
        if key in record and key not in values:
            val = _to_float(record.get(key))
            if val is not None:
                values[key] = val

    if not values:
        return None

    return Reading(
        city=str(location.get("city") or record.get("city") or ""),
        country=str(location.get("country") or record.get("country") or ""),
        timestamp=_parse_timestamp(record.get("timestamp")),
        latitude=_plain_float(location.get("latitude")),
        longitude=_plain_float(location.get("longitude")),
        sensor_type=sensor_type,
        values=values,
    )


class _TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._store: dict = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry and time.monotonic() - entry[0] < self.ttl:
            return entry[1]
        self._store.pop(key, None)
        return None

    def set(self, key, value):
        self._store[key] = (time.monotonic(), value)


class SensorsClient:
    """Async client for sensors.africa with pagination and caching."""

    def __init__(self, base_url: str = "", timeout: Optional[int] = None):
        self.data_url = base_url or config.SENSORS_DATA_URL
        self.cities_url = config.SENSORS_CITIES_URL
        self.timeout = timeout or config.SENSORS_TIMEOUT_SECONDS
        self._cache = _TTLCache(config.CACHE_TTL_SECONDS)
        self._lock = asyncio.Lock()

    async def _get_json(self, client: httpx.AsyncClient, url: str, params: Optional[dict] = None):
        response = await client.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    async def fetch_readings(
        self,
        city: str = "",
        country: str = "",
        value_type: str = "",
        max_pages: Optional[int] = None,
    ) -> list[Reading]:
        """Fetch and flatten recent readings, walking up to max_pages pages."""
        max_pages = max_pages or config.SENSORS_MAX_PAGES
        cache_key = ("readings", city.lower(), country.lower(), value_type, max_pages)
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        params = {"city": city, "country": country, "type": value_type}
        readings: list[Reading] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            url: Optional[str] = self.data_url
            for page in range(max_pages):
                if not url:
                    break
                try:
                    payload = await self._get_json(client, url, params=params if page == 0 else None)
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("sensors.africa request failed (%s): %s", url, exc)
                    break
                if isinstance(payload, dict):
                    records = payload.get("results") or []
                    url = payload.get("next")
                elif isinstance(payload, list):
                    records, url = payload, None
                else:
                    break
                for record in records:
                    reading = parse_record(record)
                    if reading is not None:
                        readings.append(reading)

        async with self._lock:
            self._cache.set(cache_key, readings)
        return readings

    async def list_cities(self) -> list[str]:
        """Cities known to the network: live endpoint merged with the seed list."""
        async with self._lock:
            cached = self._cache.get("cities")
            if cached is not None:
                return cached

        cities = set(KNOWN_CITIES)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                payload = await self._get_json(client, self.cities_url)
            items = payload.get("results", payload) if isinstance(payload, dict) else payload
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and item.strip():
                        cities.add(item.strip())
                    elif isinstance(item, dict):
                        name = item.get("name") or item.get("city") or item.get("slug")
                        if name:
                            cities.add(str(name).strip())
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("cities endpoint unavailable, using seed list: %s", exc)

        result = sorted(cities)
        async with self._lock:
            self._cache.set("cities", result)
        return result
