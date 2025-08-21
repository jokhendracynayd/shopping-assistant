"""Configuration module that loads environment variables from .env.

This file is resilient to Pydantic v2 where `BaseSettings` moved to
`pydantic-settings`. It will try to import from `pydantic_settings` first
and fall back to the old import for v1 compatibility.
"""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_keys: str = ""
    api_key_header_name: str = "x-api-key"
    require_api_key: bool = True
    # Logging controls
    logging_enabled: bool = True
    log_level: str = "INFO"
    log_dir: str = "app/log"
    # Redis / caching
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300
    redis_max_connections: int = 10
    # LLM settings
    default_temperature: float = 0.0
    # OpenAI API key
    OPENAI_API_KEY: str = ""
    # Groq API key
    GROQ_API_KEY: str = ""
    # Anthropic API key
    ANTHROPIC_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()


def get_allowed_api_keys() -> List[str]:
    if not settings.api_keys:
        return []
    return [k.strip() for k in settings.api_keys.split(",") if k.strip()]


