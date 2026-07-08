from datetime import datetime, timedelta, timezone

from app.insights import compute_trend, rank_cities, summarize_city
from app.sensors_client import Reading, parse_record


def test_parse_record_flattens_values(raw_payload):
    reading = parse_record(raw_payload["results"][0])
    assert reading.city == "Nairobi"
    assert reading.country == "KE"
    assert reading.pm25 == 18.4
    assert reading.pm10 == 31.0
    assert reading.timestamp.tzinfo is not None


def test_parse_record_survives_garbage(raw_payload):
    # Record 11 has a bad timestamp, null location, garbage + negative values.
    garbage = parse_record(raw_payload["results"][10])
    assert garbage is None  # nothing usable → dropped


def test_parse_record_filters_sentinel_values(raw_payload):
    # Record 12 has PM2.5 of 9999 (out of range) but a valid PM10.
    reading = parse_record(raw_payload["results"][11])
    assert reading.pm25 is None
    assert reading.pm10 == 12.3


def test_summarize_city(readings):
    nairobi = [r for r in readings if r.city == "Nairobi"]
    summary = summarize_city(nairobi, "Nairobi")
    assert summary.reading_count == 4
    assert summary.sensor_count == 2
    assert summary.pm25_mean == 22.9  # (18.4+20.1+24.9+28.3)/4
    assert summary.pm25_min == 18.4
    assert summary.pm25_max == 28.3


def test_trend_detects_rise(readings):
    nairobi = [r for r in readings if r.city == "Nairobi"]
    trend = compute_trend(nairobi)
    assert trend is not None
    assert trend.direction == "rising"
    assert trend.change_percent > 0


def test_trend_needs_enough_data(readings):
    assert compute_trend(readings[:2]) is None


def test_trend_steady():
    base = datetime(2026, 7, 8, tzinfo=timezone.utc)
    flat = [
        Reading(city="X", timestamp=base + timedelta(minutes=i), values={"P2": 20.0})
        for i in range(6)
    ]
    trend = compute_trend(flat)
    assert trend.direction == "steady"


def test_rank_cities_worst_first(readings):
    ranked = rank_cities(readings)
    cities = [c for c, _, _ in ranked]
    assert cities[0] == "Lagos"           # ~54.9 mean PM2.5
    assert "Nairobi" in cities
    assert "Dar Es Salaam" not in cities  # only 1 reading → excluded


def test_rank_requires_min_readings(readings):
    ranked = rank_cities(readings)
    assert all(count >= 3 for _, _, count in ranked)
