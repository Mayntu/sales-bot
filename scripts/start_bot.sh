#!/usr/bin/env bash
# Запуск всего стека: Postgres, Redis, API, Celery worker (Docker Compose).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Нет файла .env — копирую из .env.example"
  cp .env.example .env
  echo ""
  echo "Открой .env и заполни как минимум:"
  echo "  TELEGRAM_BOT_TOKEN"
  echo "  OPENAI_API_KEY"
  echo ""
  echo "Для Docker оставь DATABASE_* и REDIS_URL как в .env.example (хосты db и redis)."
  exit 1
fi

if grep -qE '^TELEGRAM_BOT_TOKEN=\s*$' .env || grep -qE '^OPENAI_API_KEY=\s*$' .env; then
  echo "В .env пустые TELEGRAM_BOT_TOKEN или OPENAI_API_KEY — заполни их и запусти снова."
  exit 1
fi

if grep -qE 'DATABASE_URL=.*@(localhost|127\.0\.0\.1)(:|\s|$)' .env; then
  echo "Ошибка: для Docker в DATABASE_URL хост должен быть db, не localhost."
  echo "  Пример: postgresql+asyncpg://gymbot:gymbot@db:5432/gymbot"
  exit 1
fi

if grep -qE '^REDIS_URL=redis://(localhost|127\.0\.0\.1)' .env; then
  echo "Ошибка: для Docker в REDIS_URL хост должен быть redis."
  echo "  Пример: redis://redis:6379/0"
  exit 1
fi

echo "Сборка и запуск контейнеров (Ctrl+C — остановка)..."
echo ""
echo "Telegram transport вынесен в отдельный сервис bot (polling)."
echo "WEBHOOK_URL/WEBHOOK_SECRET сейчас не обязательны для запуска."
echo ""
echo "Фон:  ./scripts/start_bot.sh -d     остановка: ./scripts/stop_bot.sh"
echo ""

exec docker compose up --build "$@"
