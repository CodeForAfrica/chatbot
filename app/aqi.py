"""Turn raw particulate readings into meaning.

Converts PM2.5 / PM10 concentrations (µg/m³) into the US EPA Air Quality
Index, plain-language categories, emoji indicators, and audience-specific
health guidance, with WHO 2021 guideline comparisons.

This module is pure and dependency-free so it is easy to test and reuse.
"""

from dataclasses import dataclass
from typing import Optional

# US EPA breakpoints (2024 revision for PM2.5): (C_low, C_high, AQI_low, AQI_high)
PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 500.4, 301, 500),
]

PM10_BREAKPOINTS = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 604, 301, 500),
]

# WHO 2021 Air Quality Guidelines, 24-hour means (µg/m³).
WHO_24H_PM25 = 15.0
WHO_24H_PM10 = 45.0

CATEGORIES = [
    (50, "Good", "🟢"),
    (100, "Moderate", "🟡"),
    (150, "Unhealthy for sensitive groups", "🟠"),
    (200, "Unhealthy", "🔴"),
    (300, "Very unhealthy", "🟣"),
    (500, "Hazardous", "🟤"),
]

# Advice per category index (0=Good .. 5=Hazardous) and audience.
_ADVICE = {
    "general": [
        "Air quality is good — enjoy outdoor activities.",
        "Air quality is acceptable. Unusually sensitive people should consider shorter outdoor exertion.",
        "Sensitive groups (children, elderly, people with asthma or heart conditions) should reduce prolonged outdoor exertion.",
        "Everyone should reduce prolonged outdoor exertion. Sensitive groups should stay indoors where possible.",
        "Avoid outdoor exertion. Keep windows closed; wear a well-fitting mask (e.g. N95) if you must go out.",
        "Health emergency conditions. Everyone should stay indoors with windows closed.",
    ],
    "children": [
        "It's a good time for kids to walk, play and be outside.",
        "Fine for the walk to school. If your child has asthma, keep their inhaler handy.",
        "Limit your child's time outdoors and choose calmer activities. Children breathe faster and take in more polluted air.",
        "Keep children indoors where possible; if they must be outside, keep it brief and avoid busy roads.",
        "Keep children indoors with windows closed. A well-fitting mask helps for unavoidable trips.",
        "Keep children indoors. Seek medical help promptly if a child has trouble breathing.",
    ],
    "exercise": [
        "Great conditions for a run or outdoor workout.",
        "Fine for exercise. Very sensitive people may prefer lighter sessions.",
        "Consider a shorter or less intense workout, ideally away from traffic, or exercise indoors.",
        "Move your workout indoors — heavy breathing multiplies the pollution dose.",
        "Do not exercise outdoors.",
        "Do not exercise outdoors.",
    ],
    "outdoor_workers": [
        "Normal working conditions.",
        "Normal working conditions for most people.",
        "Take more breaks away from traffic; workers with asthma should keep medication close.",
        "Reduce heavy outdoor labour where possible; a well-fitting mask (N95) helps.",
        "Limit outdoor shifts and wear a well-fitting respirator mask.",
        "Outdoor work should stop except for emergencies.",
    ],
}


@dataclass
class AqiResult:
    aqi: int
    category: str
    emoji: str
    pollutant: str
    concentration: float

    @property
    def category_index(self) -> int:
        for i, (limit, _, _) in enumerate(CATEGORIES):
            if self.aqi <= limit:
                return i
        return len(CATEGORIES) - 1


def _interpolate(conc: float, breakpoints) -> int:
    top = breakpoints[-1]
    if conc >= top[1]:
        return top[3]
    for c_low, c_high, a_low, a_high in breakpoints:
        if c_low <= conc <= c_high:
            return round((a_high - a_low) / (c_high - c_low) * (conc - c_low) + a_low)
    return 0


def aqi_from_pm25(conc: float) -> AqiResult:
    conc = max(0.0, conc)
    aqi = _interpolate(round(conc, 1), PM25_BREAKPOINTS)
    limit, category, emoji = _category_for(aqi)
    return AqiResult(aqi=aqi, category=category, emoji=emoji, pollutant="PM2.5", concentration=conc)


def aqi_from_pm10(conc: float) -> AqiResult:
    conc = max(0.0, conc)
    aqi = _interpolate(round(conc), PM10_BREAKPOINTS)
    limit, category, emoji = _category_for(aqi)
    return AqiResult(aqi=aqi, category=category, emoji=emoji, pollutant="PM10", concentration=conc)


def _category_for(aqi: int):
    for limit, category, emoji in CATEGORIES:
        if aqi <= limit:
            return limit, category, emoji
    return CATEGORIES[-1]


def combined_aqi(pm25: Optional[float], pm10: Optional[float]) -> Optional[AqiResult]:
    """AQI is reported for the dominant (worse) pollutant."""
    results = []
    if pm25 is not None:
        results.append(aqi_from_pm25(pm25))
    if pm10 is not None:
        results.append(aqi_from_pm10(pm10))
    if not results:
        return None
    return max(results, key=lambda r: r.aqi)


def health_advice(result: AqiResult, audience: str = "general") -> str:
    advice = _ADVICE.get(audience, _ADVICE["general"])
    return advice[result.category_index]


def who_comparison(pm25: Optional[float] = None, pm10: Optional[float] = None) -> str:
    """One-line comparison against WHO 2021 24-hour guidelines."""
    parts = []
    if pm25 is not None:
        ratio = pm25 / WHO_24H_PM25
        if ratio > 1:
            parts.append(f"PM2.5 is {ratio:.1f}× the WHO daily guideline ({WHO_24H_PM25:.0f} µg/m³)")
        else:
            parts.append("PM2.5 is within the WHO daily guideline")
    if pm10 is not None:
        ratio = pm10 / WHO_24H_PM10
        if ratio > 1:
            parts.append(f"PM10 is {ratio:.1f}× the WHO daily guideline ({WHO_24H_PM10:.0f} µg/m³)")
        else:
            parts.append("PM10 is within the WHO daily guideline")
    return "; ".join(parts) + "." if parts else ""
