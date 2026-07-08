from app.whatsapp import clip, extract_meta_messages, twiml_response


def test_twiml_escapes_xml():
    xml = twiml_response("PM2.5 <15 µg/m³ & rising")
    assert "&lt;15" in xml
    assert "&amp;" in xml
    assert xml.startswith('<?xml version="1.0"')


def test_clip_long_message():
    clipped = clip("x" * 5000)
    assert len(clipped) <= 3500
    assert clipped.endswith("…")


def test_extract_meta_messages():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [
                        {"type": "text", "from": "254700000001",
                         "text": {"body": "air in Nairobi"}},
                        {"type": "image", "from": "254700000002"},
                    ]
                }
            }]
        }]
    }
    messages = extract_meta_messages(payload)
    assert messages == [{"from": "254700000001", "text": "air in Nairobi"}]


def test_extract_meta_handles_status_only_payload():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "read"}]}}]}]}
    assert extract_meta_messages(payload) == []
