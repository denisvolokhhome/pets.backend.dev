"""Conversation list previews never show the raw JSON of server-made cards."""
import json

from app.services.message_service import message_preview


def test_documents_card_preview():
    assert message_preview(json.dumps({"__type": "documents", "documents": [{"id": 1}]})) == "📄 Shared documents"


def test_location_card_preview():
    assert message_preview(json.dumps({"__type": "location", "name": "Farm"})) == "📍 Shared Location"


def test_text_is_truncated_to_100_chars():
    assert message_preview("hi") == "hi"
    assert message_preview("x" * 150) == "x" * 100 + "..."
    assert message_preview('{"not": "a card"}') == '{"not": "a card"}'
    assert message_preview("") == ""
