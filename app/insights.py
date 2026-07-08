"""Statistics over sensor readings: summaries, trends, rankings, comparisons.

Pure functions over lists of Reading objects — no I/O — so every insight
the bot states is unit-testable.
"""

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Optional

from .sensors_client import Reading


@dataclass
class CitySummary:
    city: str
    sensor_count: int
    reading_count: int
    pm25_mean: Optional[float] = None
    pm25_median: Optional[float] = None
    pm25_min: Optional[float] = None
    pm25_max: Optional[float] = None
    pm10_mean: Optional[float] = None
    pm10_median: Optional[float] = None
    latest: Optional[datetime] = None


@dataclass
class Trend:
    direction: str          # "rising" | "falling" | "steady"
    change_percent: float   # signed change from earlier to later window
    earlier_mean: float
    later_mean: float
    reading_count: int


def _values(readings: list[Reading], key: str) -> list[float]:
    return [r.values[key] for r in readings if key in r.values]


def summarize_city(readings: list[Reading], city: str = "") -> CitySummary:
    pm25 = _values(readings, "P2")
    pm10 = _values(readings, "P1")
    timestamps = [r.timestamp for r in readings if r.timestamp]
    locations = {(r.latitude, r.longitude) for r in readings if r.latitude is not None}
    return CitySummary(
        city=city or (readings[0].city if readings else ""),
        sensor_count=len(locations) or (1 if readings else 0),
        reading_count=len(readings),
        pm25_mean=round(mean(pm25), 1) if pm25 else None,
        pm25_median=round(median(pm25), 1) if pm25 else None,
        pm25_min=round(min(pm25), 1) if pm25 else None,
        pm25_max=round(max(pm25), 1) if pm25 else None,
        pm10_mean=round(mean(pm10), 1) if pm10 else None,
        pm10_median=round(median(pm10), 1) if pm10 else None,
        latest=max(timestamps) if timestamps else None,
    )


def compute_trend(readings: list[Reading], key: str = "P2") -> Optional[Trend]:
    """Compare the older half of the window against the newer half.

    Honest about its basis: this is a short-window trend over whatever the
    API returned, not a climatological statement.
    """
    timed = sorted(
        (r for r in readings if r.timestamp and key in r.values),
        key=lambda r: r.timestamp,
    )
    if len(timed) < 4:
        return None
    midpoint = len(timed) // 2
    earlier = [r.values[key] for r in timed[:midpoint]]
    later = [r.values[key] for r in timed[midpoint:]]
    earlier_mean, later_mean = mean(earlier), mean(later)
    if earlier_mean == 0:
        return None
    change = (later_mean - earlier_mean) / earlier_mean * 100
    if abs(change) < 10:
        direction = "steady"
    elif change > 0:
        direction = "rising"
    else:
        direction = "falling"
    return Trend(
        direction=direction,
        change_percent=round(change, 1),
        earlier_mean=round(earlier_mean, 1),
        later_mean=round(later_mean, 1),
        reading_count=len(timed),
    )


def rank_cities(readings: list[Reading], key: str = "P2") -> list[tuple[str, float, int]]:
    """Cities ranked worst-first by mean concentration.

    Returns (city, mean, reading_count) tuples; skips unnamed cities and
    cities with fewer than 3 readings to avoid single-sensor noise.
    """
    by_city: dict[str, list[float]] = {}
    for r in readings:
        if r.city and key in r.values:
            by_city.setdefault(r.city.strip().title(), []).append(r.values[key])
    ranked = [
        (city, round(mean(vals), 1), len(vals))
        for city, vals in by_city.items()
        if len(vals) >= 3
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def compare_cities(
    readings_a: list[Reading], city_a: str,
    readings_b: list[Reading], city_b: str,
) -> tuple[CitySummary, CitySummary]:
    return summarize_city(readings_a, city_a), summarize_city(readings_b, city_b)
