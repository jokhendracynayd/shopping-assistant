"""Configuration module that loads environment variables from .env.

Enhanced with environment-specific configuration support.
"""


from pydantic_settings import BaseSettings

from app.config.environment import get_environment_config


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
    llm_timeout_seconds: int = 30
    # OpenAI API key
    OPENAI_API_KEY: str = ""
    # Groq API key
    GROQ_API_KEY: str = ""
    # Anthropic API key
    ANTHROPIC_API_KEY: str = ""
    # Weaviate settings
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    weaviate_timeout_seconds: int = 10
    # Request timeouts
    api_request_timeout_seconds: int = 60
    health_check_timeout_seconds: int = 5
    # Rate limiting
    rate_limiting_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000

    class Config:
        env_file = ".env"

    def apply_environment_overrides(self):
        """Apply environment-specific configuration overrides."""
        try:
            env_config = get_environment_config()

            # Apply environment-specific overrides
            if hasattr(env_config, "logging_enabled"):
                self.logging_enabled = env_config.logging_enabled
            if hasattr(env_config, "log_level"):
                self.log_level = env_config.log_level
            if hasattr(env_config, "require_api_key"):
                self.require_api_key = env_config.require_api_key
            if hasattr(env_config, "rate_limiting_enabled"):
                self.rate_limiting_enabled = env_config.rate_limiting_enabled
            if hasattr(env_config, "redis_max_connections"):
                self.redis_max_connections = env_config.redis_max_connections
            if hasattr(env_config, "default_temperature"):
                self.default_temperature = env_config.default_temperature
            if hasattr(env_config, "llm_timeout_seconds"):
                self.llm_timeout_seconds = env_config.llm_timeout_seconds
            if hasattr(env_config, "api_request_timeout_seconds"):
                self.api_request_timeout_seconds = env_config.api_request_timeout_seconds
            if hasattr(env_config, "cache_ttl_seconds"):
                self.cache_ttl_seconds = env_config.cache_ttl_seconds
            if hasattr(env_config, "weaviate_timeout_seconds"):
                self.weaviate_timeout_seconds = env_config.weaviate_timeout_seconds
            if hasattr(env_config, "health_check_timeout_seconds"):
                self.health_check_timeout_seconds = env_config.health_check_timeout_seconds
            if hasattr(env_config, "rate_limit_requests_per_minute"):
                self.rate_limit_requests_per_minute = env_config.rate_limit_requests_per_minute
            if hasattr(env_config, "rate_limit_requests_per_hour"):
                self.rate_limit_requests_per_hour = env_config.rate_limit_requests_per_hour

        except Exception as e:
            # Don't fail if environment config is not available
            import logging

            logging.warning(f"Failed to apply environment overrides: {e}")


# Create settings instance and apply environment overrides
settings = Settings()
settings.apply_environment_overrides()


def get_allowed_api_keys() -> list[str]:
    if not settings.api_keys:
        return []
    return [k.strip() for k in settings.api_keys.split(",") if k.strip()]
