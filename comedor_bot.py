#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

DEFAULT_MENU_URL = "https://sacu.us.es/menuSemanal?i=1"
USER_AGENT = "comedor-bot/1.0 (+https://sacu.us.es/menuSemanal?i=1)"
DEFAULT_ENV_PATH = ".env"
DEFAULT_SUBSCRIBERS_PATH = "subscribers.json"
DEFAULT_STATE_PATH = "bot_state.json"


@dataclass(frozen=True)
class DayMenu:
    label: str
    menu_date: date
    first_courses: list[str]
    second_courses: list[str]
    desserts: list[str]


@dataclass(frozen=True)
class WeeklyMenu:
    campus: str
    week_label: str
    days: list[DayMenu]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def split_menu_lines(cell_html: str) -> list[str]:
    text = strip_tags(cell_html)
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        items.append(re.sub(r"^-\s*", "", line).strip())
    return items


def parse_weekly_menu(page_html: str) -> WeeklyMenu:
    table_match = re.search(r"<table>(.*?)</table>", page_html, flags=re.IGNORECASE | re.DOTALL)
    if not table_match:
        raise ValueError("No se ha encontrado la estructura esperada del menú semanal.")

    header_html = page_html[: table_match.start()]
    campus_matches = re.findall(r"<h3>(.*?)</h3>", header_html, flags=re.IGNORECASE | re.DOTALL)
    week_matches = re.findall(r"<h4>(.*?)</h4>", header_html, flags=re.IGNORECASE | re.DOTALL)

    if not campus_matches or not week_matches:
        raise ValueError("No se ha encontrado la estructura esperada del menú semanal.")

    campus = strip_tags(campus_matches[-1])
    week_label = strip_tags(week_matches[-1])
    table_html = table_match.group(1)

    row_pattern = re.compile(
        r'<tr>\s*<th[^>]*colspan=3[^>]*>(.*?)</th>\s*</tr>\s*'
        r'<tr>\s*<th[^>]*>.*?</th>\s*<th[^>]*>.*?</th>\s*<th[^>]*>.*?</th>\s*</tr>\s*'
        r'<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    days: list[DayMenu] = []
    for header_html, first_html, second_html, dessert_html in row_pattern.findall(table_html):
        header_text = strip_tags(header_html)
        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", header_text)
        if not date_match:
            continue

        parsed_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
        day_label = header_text[: header_text.find(date_match.group(1))].strip()
        days.append(
            DayMenu(
                label=day_label,
                menu_date=parsed_date,
                first_courses=split_menu_lines(first_html),
                second_courses=split_menu_lines(second_html),
                desserts=split_menu_lines(dessert_html),
            )
        )

    if not days:
        raise ValueError("No se han podido extraer los días del menú semanal.")

    return WeeklyMenu(campus=campus, week_label=week_label, days=days)


def format_section(title: str, items: Iterable[str]) -> str:
    lines = [f"{title}:"]
    lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def format_html_section(title: str, items: Iterable[str]) -> str:
    escaped_items = [html.escape(item) for item in items]
    return "\n".join([f"<b>{html.escape(title)}</b>"] + [f"• {item}" for item in escaped_items])


def strip_html_for_console(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>\s*<p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>\s*<div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def find_day_menu(weekly_menu: WeeklyMenu, target_date: date) -> DayMenu | None:
    for day_menu in weekly_menu.days:
        if day_menu.menu_date == target_date:
            return day_menu
    return None


def build_message(weekly_menu: WeeklyMenu, day_menu: DayMenu | None, target_date: date, source_url: str) -> str:
    header = f"🍽️ <b>Menu comedor US</b> - {target_date.strftime('%d/%m/%Y')}"
    location = f"📍 {html.escape(weekly_menu.campus)}\n🗓️ {html.escape(weekly_menu.week_label)}"

    if day_menu is None:
        body = "<i>No hay menu publicado para esa fecha.</i>"
    else:
        body = "\n\n".join(
            [
                format_html_section("Primer plato", day_menu.first_courses),
                format_html_section("Segundo plato", day_menu.second_courses),
                format_html_section("Postre", day_menu.desserts),
            ]
        )

    return f"{header}\n{location}\n\n{body}\n\n<a href=\"{html.escape(source_url, quote=True)}\">Fuente</a>"


def load_env_file(env_path: str) -> None:
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)


def load_json_file(path: str, default: dict) -> dict:
    if not os.path.exists(path):
        return json.loads(json.dumps(default))
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def save_json_file(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)
        file_handle.write("\n")


def normalize_command(text: str) -> str:
    command = text.strip().split()[0].lower()
    return command.split("@", 1)[0]


def build_subscriber(chat_id: str, name: str, username: str | None, active: bool, source: str) -> dict:
    return {
        "chat_id": str(chat_id),
        "name": name,
        "username": username or "",
        "active": active,
        "source": source,
        "updated_at": now_iso(),
    }


def upsert_subscriber(subscribers: list[dict], chat_id: str, name: str, username: str | None, active: bool, source: str) -> None:
    chat_id = str(chat_id)
    for subscriber in subscribers:
        if str(subscriber.get("chat_id")) == chat_id:
            subscriber["name"] = name
            subscriber["username"] = username or ""
            subscriber["active"] = active
            subscriber["source"] = source
            subscriber["updated_at"] = now_iso()
            return
    subscribers.append(build_subscriber(chat_id=chat_id, name=name, username=username, active=active, source=source))


def ensure_default_subscriber(subscribers: list[dict], default_chat_id: str | None) -> None:
    if not default_chat_id:
        return

    for subscriber in subscribers:
        if str(subscriber.get("chat_id")) == str(default_chat_id):
            subscriber["active"] = True
            subscriber["updated_at"] = now_iso()
            subscriber.setdefault("source", "env")
            subscriber.setdefault("name", "Propietario")
            subscriber.setdefault("username", "")
            return

    subscribers.append(
        build_subscriber(
            chat_id=str(default_chat_id),
            name="Propietario",
            username=None,
            active=True,
            source="env",
        )
    )


def get_active_chat_ids(subscribers: list[dict]) -> list[str]:
    return [str(subscriber["chat_id"]) for subscriber in subscribers if subscriber.get("active")]


def extract_user_data(message: dict) -> tuple[str, str, str | None] | None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None

    user = message.get("from") or {}
    first_name = (user.get("first_name") or "").strip()
    last_name = (user.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    username = user.get("username")
    return str(chat_id), full_name or username or str(chat_id), username


def delete_telegram_message(bot_token: str, chat_id: str, message_id: int) -> None:
    telegram_api_request(
        bot_token,
        "deleteMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )


def get_last_sent_message_id(state_data: dict, chat_id: str) -> int | None:
    sent_messages = state_data.setdefault("sent_messages", {})
    raw_value = sent_messages.get(str(chat_id))
    if raw_value is None:
        return None
    return int(raw_value)


def set_last_sent_message_id(state_data: dict, chat_id: str, message_id: int) -> None:
    sent_messages = state_data.setdefault("sent_messages", {})
    sent_messages[str(chat_id)] = int(message_id)


def clear_last_sent_message_id(state_data: dict, chat_id: str) -> None:
    sent_messages = state_data.setdefault("sent_messages", {})
    sent_messages.pop(str(chat_id), None)


def process_subscription_updates(bot_token: str, subscribers_path: str, state_path: str, default_chat_id: str | None) -> list[dict]:
    subscribers_data = load_json_file(subscribers_path, {"subscribers": []})
    state_data = load_json_file(state_path, {"last_update_id": 0, "sent_messages": {}})

    subscribers = subscribers_data.setdefault("subscribers", [])
    ensure_default_subscriber(subscribers, default_chat_id)

    updates = telegram_api_request(
        bot_token,
        "getUpdates",
        {"offset": int(state_data.get("last_update_id", 0)) + 1, "timeout": 0, "allowed_updates": json.dumps(["message"])},
    )

    max_update_id = int(state_data.get("last_update_id", 0))
    for update in updates.get("result", []):
        update_id = int(update.get("update_id", 0))
        max_update_id = max(max_update_id, update_id)
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            continue

        user_data = extract_user_data(message)
        if user_data is None:
            continue

        chat_id, name, username = user_data
        command = normalize_command(text)
        if command == "/start":
            upsert_subscriber(subscribers, chat_id=chat_id, name=name, username=username, active=True, source="telegram")
        elif command == "/stop":
            upsert_subscriber(subscribers, chat_id=chat_id, name=name, username=username, active=False, source="telegram")

    state_data["last_update_id"] = max_update_id
    save_json_file(subscribers_path, subscribers_data)
    save_json_file(state_path, state_data)
    return subscribers


def telegram_api_request(bot_token: str, method: str, params: dict[str, object]) -> dict:
    payload = urllib.parse.urlencode(params).encode("utf-8")
    endpoint = f"https://api.telegram.org/bot{bot_token}/{method}"
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        response_body = response.read().decode("utf-8", errors="replace")

    parsed = json.loads(response_body)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API devolvio un error en {method}: {response_body}")
    return parsed


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> int:
    response = telegram_api_request(
        bot_token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
    )
    result = response.get("result") or {}
    return int(result["message_id"])


def send_menu_to_subscribers(bot_token: str, state_path: str, chat_ids: list[str], text: str) -> int:
    state_data = load_json_file(state_path, {"last_update_id": 0, "sent_messages": {}})
    sent_count = 0

    for chat_id in chat_ids:
        previous_message_id = get_last_sent_message_id(state_data, chat_id)
        if previous_message_id is not None:
            try:
                delete_telegram_message(bot_token, chat_id, previous_message_id)
            except RuntimeError:
                clear_last_sent_message_id(state_data, chat_id)

        new_message_id = send_telegram_message(bot_token, chat_id, text)
        set_last_sent_message_id(state_data, chat_id, new_message_id)
        sent_count += 1

    save_json_file(state_path, state_data)
    return sent_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae el menu diario del comedor de la Universidad de Sevilla y lo envia por Telegram."
    )
    parser.add_argument(
        "--env-file",
        default=os.getenv("COMEDOR_ENV_FILE", DEFAULT_ENV_PATH),
        help="Ruta al fichero de variables de entorno. Por defecto usa .env en el directorio actual.",
    )
    parser.add_argument(
        "--subscribers-file",
        default=os.getenv("COMEDOR_SUBSCRIBERS_FILE", DEFAULT_SUBSCRIBERS_PATH),
        help="Ruta al fichero JSON de suscriptores.",
    )
    parser.add_argument(
        "--state-file",
        default=os.getenv("COMEDOR_STATE_FILE", DEFAULT_STATE_PATH),
        help="Ruta al fichero JSON con el ultimo update_id procesado.",
    )
    parser.add_argument("--url", default=os.getenv("COMEDOR_MENU_URL", DEFAULT_MENU_URL))
    parser.add_argument(
        "--date",
        default=os.getenv("COMEDOR_TARGET_DATE"),
        help="Fecha objetivo en formato YYYY-MM-DD. Por defecto usa la fecha local del sistema.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Imprime el mensaje en stdout sin enviarlo a Telegram.")
    return parser.parse_args()


def resolve_target_date(raw_date: str | None) -> date:
    if not raw_date:
        return date.today()
    return datetime.strptime(raw_date, "%Y-%m-%d").date()


def main() -> int:
    args = parse_args()

    try:
        load_env_file(args.env_file)
        target_date = resolve_target_date(args.date)
        weekly_menu = parse_weekly_menu(fetch_url(args.url))
        day_menu = find_day_menu(weekly_menu, target_date)
        message = build_message(weekly_menu, day_menu, target_date, args.url)

        if args.dry_run:
            print(strip_html_for_console(message))
            return 0

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not bot_token or not chat_id:
            raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en el entorno.")

        subscribers = process_subscription_updates(
            bot_token=bot_token,
            subscribers_path=args.subscribers_file,
            state_path=args.state_file,
            default_chat_id=chat_id,
        )
        active_chat_ids = get_active_chat_ids(subscribers)
        if not active_chat_ids:
            raise RuntimeError("No hay suscriptores activos para enviar el menu.")

        sent_count = send_menu_to_subscribers(bot_token, args.state_file, active_chat_ids, message)
        print(f"Mensaje enviado para {target_date.isoformat()} a {sent_count} suscriptor(es).")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP: {exc.code} {exc.reason}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"Error de red: {exc.reason}", file=sys.stderr)
    except ValueError as exc:
        print(f"Error de parseo: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
