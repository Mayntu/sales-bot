# Запуск Gym Sales Platform

Стек: **PostgreSQL**, **Redis**, **FastAPI (api)**, **Telegram-бот (bot, polling)**, **Celery worker + beat**.

## 1. Переменные окружения

Скопируй `.env.example` → `.env` и заполни как минимум:

| Переменная | Где нужна | Описание |
|------------|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | api, bot | Токен бота |
| `OPENAI_API_KEY` | api, worker | Ключ OpenAI |
| `DATABASE_URL` | api, worker | В Docker: `postgresql+asyncpg://gymbot:gymbot@db:5432/gymbot` |
| `REDIS_URL` | api, worker, beat | В Docker: `redis://redis:6379/0` |
| `ADMIN_SECRET` | api, bot | Один и тот же секрет для `X-Admin-Secret` и TG-админки |
| `ADMIN_TELEGRAM_CHAT_IDS` | bot | Твой `chat_id` в Telegram (через запятую, если несколько) |
| `API_INTERNAL_URL` | bot | В Docker: `http://api:8000` |
| `CLUB_INFO_PATH` | api, worker | В Docker: `club_data/club_info.yaml` |

Узнать свой `chat_id`: напиши боту [@userinfobot](https://t.me/userinfobot) или посмотри логи при первом сообщении.

## 2. Docker Compose

Из корня репозитория:

```bash
docker compose up --build
```

Поднимутся: `db`, `redis`, `api` (порт **8000**), `bot`, `worker`, `beat`.

Проверка API: открой `http://localhost:8000/health`.

## 3. Админка в Telegram

Нужны **оба** значения: `ADMIN_SECRET` и `ADMIN_TELEGRAM_CHAT_IDS` (твой id).

Команды (только для указанных chat_id):

- `/a_help` — справка
- `/a_discounts` — скидки дня из `club_info.yaml`
- `/a_discount_set id цена лейбл; id2 цена2 лейбл2` — задать скидки на сегодня
- `/a_discount_clear` — убрать все скидки дня
- `/a_price gold 180000` — обновить `base_price` у абонемента
- `/a_temp` — временные абонементы
- `/a_stats` — статистика лидов

Обычные сообщения клиентов идут в AI через `POST /v1/chat` как раньше.

## 4. Частая ошибка при старте API

Если в логах была ошибка Pydantic про `date | None` в `DailyDiscounts`: она исправлена — поле из YAML `date` маппится на `valid_on`, чтобы не затенять тип `date` из `datetime`.
