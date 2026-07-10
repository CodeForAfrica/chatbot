"""Auth-header construction for the sensors.africa client.

These tests use a placeholder token — never a real key.
"""

from app import config
from app.sensors_client import _auth_headers


def test_no_key_sends_no_authorization(monkeypatch):
    monkeypatch.setattr(config, "SENSORS_API_KEY", "")
    headers = _auth_headers()
    assert "Authorization" not in headers
    assert headers["Accept"] == "application/json"
    assert "User-Agent" in headers


def test_token_scheme_default(monkeypatch):
    monkeypatch.setattr(config, "SENSORS_API_KEY", "PLACEHOLDER_TOKEN")
    monkeypatch.setattr(config, "SENSORS_API_KEY_SCHEME", "Token")
    assert _auth_headers()["Authorization"] == "Token PLACEHOLDER_TOKEN"


def test_bearer_scheme(monkeypatch):
    monkeypatch.setattr(config, "SENSORS_API_KEY", "PLACEHOLDER_TOKEN")
    monkeypatch.setattr(config, "SENSORS_API_KEY_SCHEME", "Bearer")
    assert _auth_headers()["Authorization"] == "Bearer PLACEHOLDER_TOKEN"


def test_empty_scheme_sends_raw_key(monkeypatch):
    monkeypatch.setattr(config, "SENSORS_API_KEY", "PLACEHOLDER_TOKEN")
    monkeypatch.setattr(config, "SENSORS_API_KEY_SCHEME", "")
    assert _auth_headers()["Authorization"] == "PLACEHOLDER_TOKEN"
