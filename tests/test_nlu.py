import pytest

from app.nlu import extract_cities, parse
from app.sensors_client import KNOWN_CITIES


def test_greeting():
    assert parse("Hello!", KNOWN_CITIES).name == "greeting"
    assert parse("habari", KNOWN_CITIES).name == "greeting"


def test_help():
    assert parse("help", KNOWN_CITIES).name == "help"
    assert parse("what can you do?", KNOWN_CITIES).name == "help"


def test_air_quality_with_city():
    intent = parse("How is the air quality in Nairobi?", KNOWN_CITIES)
    assert intent.name == "air_quality"
    assert intent.city == "Nairobi"


def test_city_only_message():
    intent = parse("Lagos", KNOWN_CITIES)
    assert intent.name == "air_quality"
    assert intent.city == "Lagos"


def test_fuzzy_city_typo():
    cities = extract_cities("air in Nairbi today", KNOWN_CITIES)
    assert cities == ["Nairobi"]


def test_multiword_city():
    intent = parse("pollution in Dar es Salaam", KNOWN_CITIES)
    assert intent.city == "Dar es Salaam"


def test_health_for_children():
    intent = parse("Is it safe for my kids to walk to school in Lagos?", KNOWN_CITIES)
    assert intent.name == "health"
    assert intent.city == "Lagos"
    assert intent.audience == "children"


def test_health_for_runners_uses_context_city():
    intent = parse("can I go for a run?", KNOWN_CITIES, last_city="Nairobi")
    assert intent.name == "health"
    assert intent.city == "Nairobi"
    assert intent.audience == "exercise"


def test_compare_two_cities():
    intent = parse("compare Nairobi vs Lagos", KNOWN_CITIES)
    assert intent.name == "compare"
    assert {intent.city, intent.second_city} == {"Nairobi", "Lagos"}


def test_rank_worst():
    intent = parse("which city is the most polluted?", KNOWN_CITIES)
    assert intent.name == "rank"
    assert intent.extras["order"] == "worst"


def test_rank_best():
    intent = parse("cleanest city right now", KNOWN_CITIES)
    assert intent.name == "rank"
    assert intent.extras["order"] == "best"


def test_trend():
    intent = parse("is the air in Accra getting better?", KNOWN_CITIES)
    assert intent.name == "trend"
    assert intent.city == "Accra"


def test_explain_pm25():
    intent = parse("what is pm2.5?", KNOWN_CITIES)
    assert intent.name == "explain"
    assert intent.topic == "pm25"


def test_explain_aqi():
    intent = parse("explain AQI to me", KNOWN_CITIES)
    assert intent.name == "explain"
    assert intent.topic == "aqi"


def test_list_cities():
    assert parse("which cities do you cover?", KNOWN_CITIES).name == "list_cities"


def test_air_without_city_asks():
    assert parse("how is the air today?", KNOWN_CITIES).name == "ask_city"


def test_air_without_city_uses_context():
    intent = parse("how is the air today?", KNOWN_CITIES, last_city="Kampala")
    assert intent.name == "air_quality"
    assert intent.city == "Kampala"


def test_unknown():
    assert parse("tell me a joke about giraffes", KNOWN_CITIES).name == "unknown"


def test_empty_message():
    assert parse("", KNOWN_CITIES).name == "help"
