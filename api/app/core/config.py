from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'gym-sales-api'

    # OpenAI
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o'  # основной диалог QUALIFY+
    openai_model_light: str = 'gpt-4o-mini'  # NEW привет + все follow-up (короткие сообщения по шаблонам)

    # PostgreSQL (async — FastAPI; sync URL built at runtime for Celery)
    database_url: str = 'postgresql+asyncpg://gymbot:gymbot@db:5432/gymbot'
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_recycle: int = 3600

    # Redis
    redis_url: str = 'redis://redis:6379/0'
    # Separate Redis DB for cache/rate-limit (Celery uses DB 0 via redis_url)
    redis_cache_db: int = 1

    # Auth
    manager_api_secret: str = ''
    admin_secret: str = 'change-me-in-env'

    # Telegram
    manager_chat_id: int | None = None
    telegram_bot_token: str = ''
    # chat_id через запятую — для destructive admin (удаление юзера /refresh только этим id)
    admin_chat_ids: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_CHAT_IDS", "ADMIN_TELEGRAM_CHAT_IDS"),
    )

    # App
    club_info_path: str = 'club_data/club_info.yaml'
    max_dialog_messages: int = 8

    # Rate limiting: max messages per chat per minute
    chat_rate_limit_per_minute: int = 20

    # Club context cache TTL in seconds
    club_context_cache_ttl: int = 300

    # Agent names (comma-separated). One is assigned per user deterministically.
    agent_names: str = "Саша,Данияр,Толкын"

    def get_agent_names(self) -> list[str]:
        return [n.strip() for n in self.agent_names.split(",") if n.strip()]

    def get_admin_chat_ids(self) -> frozenset[int]:
        out: list[int] = []
        for part in self.admin_chat_ids.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                out.append(int(part))
        return frozenset(out)


@lru_cache
def get_settings() -> Settings:
    return Settings()
