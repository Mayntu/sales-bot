#!/usr/bin/env python3
"""Управление вебхуком Telegram. Из корня проекта: python3 scripts/set_webhook.py set"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env_manual() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.is_file():
        print(f"Нет файла {path}", file=sys.stderr)
        sys.exit(1)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        env[k] = v
    return env


def _tg_request(
    method: str,
    token: str,
    *,
    get_params: dict[str, str] | None = None,
    post_data: dict[str, str] | None = None,
) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if get_params:
        url = f"{url}?{urlencode(get_params)}"
    if post_data is not None:
        body = urlencode(post_data).encode()
        req = Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    else:
        req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from e
    except URLError as e:
        print(f"Сеть: {e}", file=sys.stderr)
        raise SystemExit(1) from e


def cmd_set(env: dict[str, str]) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("В .env нет TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(1)
    webhook_url = env.get("WEBHOOK_URL", "").strip()
    if not webhook_url:
        print(
            "В .env нет WEBHOOK_URL. Пример:\n"
            "  WEBHOOK_URL=https://xxxx.ngrok-free.app/webhook/telegram",
            file=sys.stderr,
        )
        sys.exit(1)
    if "/webhook/telegram" not in webhook_url:
        print(
            "WEBHOOK_URL должен вести на путь /webhook/telegram.",
            file=sys.stderr,
        )
        sys.exit(1)
    secret = env.get("WEBHOOK_SECRET", "").strip()
    post: dict[str, str] = {"url": webhook_url}
    if secret:
        post["secret_token"] = secret
    data = _tg_request("setWebhook", token, post_data=post)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not data.get("ok"):
        sys.exit(1)


def cmd_delete(env: dict[str, str]) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("В .env нет TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(1)
    data = _tg_request(
        "deleteWebhook",
        token,
        get_params={"drop_pending_updates": "true"},
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_info(env: dict[str, str]) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("В .env нет TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(1)
    data = _tg_request("getWebhookInfo", token)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Telegram setWebhook / getWebhookInfo / deleteWebhook")
    p.add_argument("command", choices=("set", "info", "delete"), nargs="?", default="set")
    args = p.parse_args()
    env = _load_env_manual()
    if args.command == "set":
        cmd_set(env)
    elif args.command == "delete":
        cmd_delete(env)
    else:
        cmd_info(env)


if __name__ == "__main__":
    main()
