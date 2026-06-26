from datetime import date
from urllib.error import HTTPError

from comedor_bot import (
    build_message,
    find_day_menu,
    get_active_chat_ids,
    get_last_sent_message_id,
    load_env_file,
    parse_weekly_menu,
    process_subscription_updates,
    send_menu_to_subscribers,
    strip_html_for_console,
    telegram_api_request,
)

SAMPLE_HTML = """
<div class="field-item even">
  <h3>Campus de Cartuja (Facultad de Comunicación)</h3>
  <h4>Menú semanal: 15/06/2026 - 19/06/2026</h4>
  <table>
    <tr><th style="text-align:center; background-color:#951419; color:#fff" colspan=3><strong>LUNES 15/06/2026</strong></th></tr>
    <tr><th><strong>Primer plato</strong></th><th><strong>Segundo plato</strong></th><th><strong>Postre</strong></th></tr>
    <tr>
      <td>- Lentejas con calabaza y curry<br/>- Patatas aliñadas<br/></td>
      <td>- Calamares fritos<br/>- Chuleta de cerdo a la pimienta<br/></td>
      <td>- Fruta fresca<br/>- Postre casero/lácteo<br/></td>
    </tr>
    <tr><th style="text-align:center; background-color:#951419; color:#fff" colspan=3><span style="color:#fff;font-weight:bold;">MARTES 16/06/2026</span></th></tr>
    <tr><th><strong>Primer plato</strong></th><th><strong>Segundo plato</strong></th><th><strong>Postre</strong></th></tr>
    <tr>
      <td>- Ensalada de pasta<br/>- Guisantes<br/></td>
      <td>- Filete de cerdo en salsa verde<br/>- Fritura de boquerones<br/></td>
      <td>- Fruta fresca<br/>- Postre casero/lácteo <br/></td>
    </tr>
  </table>
</div>
"""


def test_parse_weekly_menu_extracts_columns():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)

    assert weekly_menu.campus == "Campus de Cartuja (Facultad de Comunicación)"
    assert weekly_menu.week_label == "Menú semanal: 15/06/2026 - 19/06/2026"
    assert len(weekly_menu.days) == 2
    assert weekly_menu.days[1].label == "MARTES"
    assert weekly_menu.days[1].menu_date == date(2026, 6, 16)
    assert weekly_menu.days[1].first_courses == ["Ensalada de pasta", "Guisantes"]
    assert weekly_menu.days[1].second_courses == ["Filete de cerdo en salsa verde", "Fritura de boquerones"]
    assert weekly_menu.days[1].desserts == ["Fruta fresca", "Postre casero/lácteo"]


def test_build_message_for_existing_day():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)
    day_menu = find_day_menu(weekly_menu, date(2026, 6, 16))

    message = build_message(weekly_menu, day_menu, date(2026, 6, 16), "https://sacu.us.es/menuSemanal?i=1")

    assert "<b>Menu comedor US</b> - 16/06/2026" in message
    assert "<b>Primer plato</b>\n• Ensalada de pasta\n• Guisantes" in message
    assert "<b>Segundo plato</b>\n• Filete de cerdo en salsa verde\n• Fritura de boquerones" in message
    assert "<b>Postre</b>\n• Fruta fresca\n• Postre casero/lácteo" in message
    assert "<a href=\"https://sacu.us.es/menuSemanal?i=1\">Fuente</a>" in message


def test_build_message_when_day_is_missing():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)

    message = build_message(weekly_menu, None, date(2026, 6, 20), "https://sacu.us.es/menuSemanal?i=1")

    assert "<i>No hay menu publicado para esa fecha.</i>" in message


def test_strip_html_for_console_keeps_readable_preview():
    text = strip_html_for_console("<b>Primer plato</b>\n• Ensalada\n• Gazpacho\n\n<a href=\"https://example.com\">Fuente</a>")

    assert "Primer plato" in text
    assert "• Ensalada" in text
    assert "Fuente" in text


def test_load_env_file_sets_missing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text('TELEGRAM_BOT_TOKEN="abc"\nexport TELEGRAM_CHAT_ID=123\n', encoding="utf-8")

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    load_env_file(str(env_path))

    assert "abc" == __import__("os").environ["TELEGRAM_BOT_TOKEN"]
    assert "123" == __import__("os").environ["TELEGRAM_CHAT_ID"]


def test_process_subscription_updates_registers_start_and_stop(tmp_path, monkeypatch):
    subscribers_path = tmp_path / "subscribers.json"
    state_path = tmp_path / "bot_state.json"

    updates_payload = {
        "ok": True,
        "result": [
            {
                "update_id": 101,
                "message": {
                    "text": "/start",
                    "chat": {"id": 111},
                    "from": {"first_name": "Ana", "last_name": "Lopez", "username": "ana"},
                },
            },
            {
                "update_id": 102,
                "message": {
                    "text": "/stop",
                    "chat": {"id": 222},
                    "from": {"first_name": "Luis", "username": "luis"},
                },
            },
        ],
    }

    def fake_telegram_api_request(bot_token, method, params):
        assert bot_token == "token"
        assert method == "getUpdates"
        assert params["offset"] == 1
        return updates_payload

    monkeypatch.setattr("comedor_bot.telegram_api_request", fake_telegram_api_request)

    subscribers = process_subscription_updates(
        bot_token="token",
        subscribers_path=str(subscribers_path),
        state_path=str(state_path),
        default_chat_id="999",
    )

    assert get_active_chat_ids(subscribers) == ["999", "111"]
    assert any(item["chat_id"] == "111" and item["name"] == "Ana Lopez" and item["active"] for item in subscribers)
    assert any(item["chat_id"] == "222" and item["name"] == "Luis" and not item["active"] for item in subscribers)
    assert __import__("json").loads(state_path.read_text(encoding="utf-8"))["last_update_id"] == 102


def test_process_subscription_updates_uses_existing_offset(tmp_path, monkeypatch):
    subscribers_path = tmp_path / "subscribers.json"
    state_path = tmp_path / "bot_state.json"
    state_path.write_text('{"last_update_id": 40}\n', encoding="utf-8")

    def fake_telegram_api_request(bot_token, method, params):
        assert params["offset"] == 41
        return {"ok": True, "result": []}

    monkeypatch.setattr("comedor_bot.telegram_api_request", fake_telegram_api_request)

    subscribers = process_subscription_updates(
        bot_token="token",
        subscribers_path=str(subscribers_path),
        state_path=str(state_path),
        default_chat_id="999",
    )

    assert get_active_chat_ids(subscribers) == ["999"]


def test_send_menu_to_subscribers_replaces_previous_messages(tmp_path, monkeypatch):
    state_path = tmp_path / "bot_state.json"
    state_path.write_text('{"last_update_id": 10, "sent_messages": {"111": 500}}\n', encoding="utf-8")
    calls = []

    def fake_telegram_api_request(bot_token, method, params):
        calls.append((method, params))
        if method == "deleteMessage":
            return {"ok": True, "result": True}
        if method == "sendMessage":
            if params["chat_id"] == "111":
                return {"ok": True, "result": {"message_id": 700}}
            return {"ok": True, "result": {"message_id": 800}}
        raise AssertionError(method)

    monkeypatch.setattr("comedor_bot.telegram_api_request", fake_telegram_api_request)

    sent_count = send_menu_to_subscribers("token", str(state_path), ["111", "222"], "hola")

    assert sent_count == 2
    assert calls[0] == ("deleteMessage", {"chat_id": "111", "message_id": 500})
    assert calls[1][0] == "sendMessage"
    assert calls[2][0] == "sendMessage"

    saved_state = __import__("json").loads(state_path.read_text(encoding="utf-8"))
    assert get_last_sent_message_id(saved_state, "111") == 700
    assert get_last_sent_message_id(saved_state, "222") == 800


def test_send_menu_to_subscribers_clears_missing_previous_message(tmp_path, monkeypatch):
    state_path = tmp_path / "bot_state.json"
    state_path.write_text('{"last_update_id": 10, "sent_messages": {"111": 500}}\n', encoding="utf-8")

    def fake_telegram_api_request(bot_token, method, params):
        if method == "deleteMessage":
            raise RuntimeError("message not found")
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 701}}
        raise AssertionError(method)

    monkeypatch.setattr("comedor_bot.telegram_api_request", fake_telegram_api_request)

    send_menu_to_subscribers("token", str(state_path), ["111"], "hola")

    saved_state = __import__("json").loads(state_path.read_text(encoding="utf-8"))
    assert get_last_sent_message_id(saved_state, "111") == 701


def test_telegram_api_request_includes_http_error_details(monkeypatch):
    class FakeHttpError(HTTPError):
        def __init__(self):
            super().__init__("https://example.com", 400, "Bad Request", hdrs=None, fp=None)

        def read(self):
            return b'{"ok":false,"description":"Bad Request: message to delete not found"}'

    def fake_urlopen(request, timeout):
        raise FakeHttpError()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    try:
        telegram_api_request("token", "deleteMessage", {"chat_id": "1", "message_id": 2})
    except RuntimeError as exc:
        assert "message to delete not found" in str(exc)
    else:
        raise AssertionError("Se esperaba RuntimeError")
