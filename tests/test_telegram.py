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


def test_parse_chat_ids_accepts_commas_and_spaces():
    from grocery_agent.telegram import parse_chat_ids

    assert parse_chat_ids("111") == ["111"]
    assert parse_chat_ids("111, 222 ,-333") == ["111", "222", "-333"]
    assert parse_chat_ids("111 222;333") == ["111", "222", "333"]
    assert parse_chat_ids("111,111") == ["111"]  # duplicates collapse
    assert parse_chat_ids("") == [] and parse_chat_ids(None) == []


def test_document_is_sent_to_every_chat():
    chats = []

    def handler(request):
        for part in request.content.split(b"\r\n"):
            if part.isdigit() or (part.startswith(b"-") and part[1:].isdigit()):
                chats.append(part.decode())
        return httpx.Response(200, json={"ok": True})

    Telegram(TOKEN, "111,222", client_with(handler)).send_document("d.html", b"<html></html>")
    assert chats == ["111", "222"]


def test_one_unreachable_chat_does_not_stop_the_others(caplog):
    delivered = []

    def handler(request):
        body = request.content
        if b"222" in body:
            return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot can't initiate conversation with a user"})
        delivered.append(body)
        return httpx.Response(200, json={"ok": True})

    with caplog.at_level("WARNING"):
        Telegram(TOKEN, "222,111", client_with(handler)).send_document("d.html", b"x")  # must not raise
    assert len(delivered) == 1
    assert "222" in caplog.text and "SECRET" not in caplog.text


def test_all_chats_failing_raises_without_leaking_the_token():
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(RuntimeError) as err:
        Telegram(TOKEN, "111,222", client_with(handler)).send_document("d.html", b"x")
    assert "chat not found" in str(err.value) and "SECRET" not in str(err.value)


def test_no_chat_ids_is_rejected_up_front():
    with pytest.raises(ValueError):
        Telegram(TOKEN, "  ", client_with(lambda r: httpx.Response(200, json={"ok": True})))
