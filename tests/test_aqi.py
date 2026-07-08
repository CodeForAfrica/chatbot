from app.aqi import (
    aqi_from_pm10,
    aqi_from_pm25,
    combined_aqi,
    health_advice,
    who_comparison,
)


def test_pm25_good():
    result = aqi_from_pm25(5.0)
    assert result.aqi <= 50
    assert result.category == "Good"
    assert result.emoji == "🟢"


def test_pm25_moderate():
    result = aqi_from_pm25(20.0)
    assert 51 <= result.aqi <= 100
    assert result.category == "Moderate"


def test_pm25_unhealthy():
    result = aqi_from_pm25(60.0)
    assert 151 <= result.aqi <= 200
    assert result.category == "Unhealthy"


def test_pm25_extreme_clamps_to_500():
    assert aqi_from_pm25(9999).aqi == 500


def test_pm10_boundaries():
    assert aqi_from_pm10(0).aqi == 0
    assert aqi_from_pm10(54).aqi == 50
    assert aqi_from_pm10(155).category == "Unhealthy for sensitive groups"


def test_negative_concentration_clamped():
    assert aqi_from_pm25(-3).aqi == 0


def test_combined_uses_dominant_pollutant():
    # PM2.5 60 → Unhealthy; PM10 30 → Good; combined must report PM2.5.
    result = combined_aqi(60.0, 30.0)
    assert result.pollutant == "PM2.5"
    assert result.category == "Unhealthy"


def test_combined_none_when_no_data():
    assert combined_aqi(None, None) is None


def test_health_advice_varies_by_audience():
    result = aqi_from_pm25(45.0)  # unhealthy for sensitive groups
    child = health_advice(result, "children")
    runner = health_advice(result, "exercise")
    assert child != runner
    assert "child" in child.lower()


def test_who_comparison_flags_exceedance():
    text = who_comparison(pm25=30.0)
    assert "2.0×" in text
    assert "within" in who_comparison(pm25=10.0)
