import pytest

from app.responder import Responder


@pytest.fixture()
def responder(fake_client):
    return Responder(client=fake_client)


@pytest.mark.anyio
async def test_greeting(responder):
    reply = await responder.reply("hello")
    assert "sensors.africa" in reply


@pytest.mark.anyio
async def test_city_snapshot_includes_numbers_and_advice(responder):
    reply = await responder.reply("air quality in Nairobi")
    assert "Nairobi" in reply
    assert "PM2.5: 22.9" in reply
    assert "AQI" in reply
    assert "💡" in reply  # health advice line


@pytest.mark.anyio
async def test_health_question_for_kids(responder):
    reply = await responder.reply("Is it safe for my kids to walk to school in Lagos?")
    assert "Lagos" in reply
    assert "child" in reply.lower() or "kid" in reply.lower()


@pytest.mark.anyio
async def test_follow_up_uses_remembered_city(responder):
    await responder.reply("air quality in Kampala", session_id="s1")
    reply = await responder.reply("is it safe to run?", session_id="s1")
    assert "Kampala" in reply


@pytest.mark.anyio
async def test_sessions_are_isolated(responder):
    await responder.reply("air quality in Kampala", session_id="s1")
    reply = await responder.reply("how is the air?", session_id="s2")
    assert "Which city" in reply


@pytest.mark.anyio
async def test_compare(responder):
    reply = await responder.reply("compare Nairobi and Lagos")
    assert "Nairobi" in reply and "Lagos" in reply
    assert "cleaner air" in reply


@pytest.mark.anyio
async def test_rank_worst(responder):
    reply = await responder.reply("most polluted city right now")
    assert "Lagos" in reply.splitlines()[1]  # Lagos tops the fixture data


@pytest.mark.anyio
async def test_trend(responder):
    reply = await responder.reply("is the air in Nairobi getting worse?")
    assert "worsening" in reply or "improving" in reply or "steady" in reply


@pytest.mark.anyio
async def test_explainer(responder):
    reply = await responder.reply("what is PM2.5?")
    assert "2.5 micrometres" in reply


@pytest.mark.anyio
async def test_no_data_city(responder):
    reply = await responder.reply("air quality in Windhoek")
    assert "couldn't find recent readings" in reply


@pytest.mark.anyio
async def test_unknown_without_llm_falls_back_to_help(responder, monkeypatch):
    monkeypatch.setattr("app.llm.available", lambda: False)
    reply = await responder.reply("write me a poem about accounting")
    assert "Air quality in Nairobi" in reply  # help text examples


@pytest.fixture
def anyio_backend():
    return "asyncio"
