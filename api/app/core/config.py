from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'gym-sales-api'

    # OpenAI
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o'

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

    # App
    club_info_path: str = 'club_data/club_info.yaml'
    max_dialog_messages: int = 20

    # Rate limiting: max messages per chat per minute
    chat_rate_limit_per_minute: int = 20

    # Club context cache TTL in seconds
    club_context_cache_ttl: int = 300

    # Agent names (comma-separated). One is assigned per user deterministically.
    agent_names: str = "Саша,Данияр,Толкын"

    def get_agent_names(self) -> list[str]:
        return [n.strip() for n in self.agent_names.split(",") if n.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
