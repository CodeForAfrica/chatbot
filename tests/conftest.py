import json
import pathlib

import pytest

from app.sensors_client import KNOWN_CITIES, Reading, parse_record

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_data.json"


@pytest.fixture(scope="session")
def raw_payload() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture()
def readings(raw_payload) -> list[Reading]:
    parsed = [parse_record(r) for r in raw_payload["results"]]
    return [r for r in parsed if r is not None]


class FakeSensorsClient:
    """Stands in for SensorsClient in tests — no network."""

    def __init__(self, readings: list[Reading]):
        self._readings = readings

    async def fetch_readings(self, city: str = "", country: str = "",
                             value_type: str = "", max_pages=None) -> list[Reading]:
        if city:
            return [r for r in self._readings if r.city.lower() == city.lower()]
        return list(self._readings)

    async def list_cities(self) -> list[str]:
        live = {r.city for r in self._readings if r.city}
        return sorted(set(KNOWN_CITIES) | live)


@pytest.fixture()
def fake_client(readings) -> FakeSensorsClient:
    return FakeSensorsClient(readings)
