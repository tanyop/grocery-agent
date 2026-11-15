import json

import httpx
import pytest

from grocery_agent.telegram import Telegram

TOKEN = "123:SECRET"


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_send_message_posts_chat_id_and_text():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    Telegram(TOKEN, "42", client_with(handler)).send_message("здравей")
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert seen["body"] == {"chat_id": "42", "text": "здравей", "disable_web_page_preview": True}


def test_send_document_uploads_file_as_multipart():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["ctype"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    Telegram(TOKEN, "42", client_with(handler)).send_document("digest.html", "<html>здрасти</html>".encode(), "подпис")
    assert seen["url"].endswith("/sendDocument")
    assert seen["ctype"].startswith("multipart/form-data")
    assert b'filename="digest.html"' in seen["body"]
    assert "здрасти".encode() in seen["body"] and "подпис".encode() in seen["body"]


def test_api_error_is_reported_without_leaking_the_token():
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(RuntimeError) as err:
        Telegram(TOKEN, "42", client_with(handler)).send_message("x")
    assert "chat not found" in str(err.value)
    assert "SECRET" not in str(err.value)


def test_network_error_does_not_leak_the_token():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(RuntimeError) as err:
        Telegram(TOKEN, "42", client_with(handler)).send_message("x")
    assert "SECRET" not in str(err.value)
    assert err.value.__cause__ is None or "SECRET" not in repr(err.value.__cause__)
