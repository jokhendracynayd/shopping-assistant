"""Environment-specific configuration management.

Loads configuration from YAML files based on the current environment,
with fallback to environment variables and defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.utils.logger import get_logger

logger = get_logger("config.environment")


class EnvironmentConfig(BaseModel):
    """Environment-specific configuration model."""

    # Application settings
    debug: bool = False
    environment: str = "development"

    # Logging
    logging_enabled: bool = True
    log_level: str = "INFO"

    # Security
    require_api_key: bool = True
    rate_limiting_enabled: bool = True

    # Database
    redis_max_connections: int = 10

    # LLM settings
    default_temperature: float = 0.0
    llm_timeout_seconds: int = 30

    # Rate limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000

    # Timeouts
    api_request_timeout_seconds: int = 60
    health_check_timeout_seconds: int = 5
    weaviate_timeout_seconds: int = 10

    # Cache
    cache_ttl_seconds: int = 300

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Features
    enable_debug_endpoints: bool = False
    enable_mock_services: bool = False
    auto_reload: bool = False
    enable_metrics: bool = False
    enable_tracing: bool = False
    enable_profiling: bool = False
    enable_security_headers: bool = True
    enable_request_logging: bool = True
    enable_audit_logging: bool = False

    # Testing
    use_test_database: bool = False
    mock_external_apis: bool = False
    fast_startup: bool = False


class ConfigLoader:
    """Load and manage environment-specific configurations."""

    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.environment = self._detect_environment()
        self._loaded_config: EnvironmentConfig | None = None

    def _detect_environment(self) -> str:
        """Detect current environment from various sources."""
        # Priority order: ENV var > command line > default
        env = os.getenv("ENVIRONMENT") or os.getenv("ENV") or os.getenv("STAGE")

        if env:
            return env.lower()

        # Detect from common CI/CD environment variables
        if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
            return "testing"

        if os.getenv("VERCEL") or os.getenv("NETLIFY"):
            return "production"

        # Default to development
        return "development"

    def _load_yaml_config(self, environment: str) -> dict[str, Any]:
        """Load configuration from YAML file."""
        config_file = self.config_dir / f"{environment}.yaml"

        if not config_file.exists():
            logger.warning(f"Configuration file not found: {config_file}")
            return {}

        try:
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_file}: {e}")
            return {}

    def _merge_with_env_vars(self, config: dict[str, Any]) -> dict[str, Any]:
        """Merge configuration with environment variables."""
        # Define mapping of config keys to environment variable names
        env_var_mapping = {
            "debug": "DEBUG",
            "logging_enabled": "LOGGING_ENABLED",
            "log_level": "LOG_LEVEL",
            "require_api_key": "REQUIRE_API_KEY",
            "rate_limiting_enabled": "RATE_LIMITING_ENABLED",
            "redis_max_connections": "REDIS_MAX_CONNECTIONS",
            "default_temperature": "DEFAULT_TEMPERATURE",
            "llm_timeout_seconds": "LLM_TIMEOUT_SECONDS",
            "api_request_timeout_seconds": "API_REQUEST_TIMEOUT_SECONDS",
            "cache_ttl_seconds": "CACHE_TTL_SECONDS",
        }

        for config_key, env_var in env_var_mapping.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert string values to appropriate types
                if config_key in [
                    "debug",
                    "logging_enabled",
                    "require_api_key",
                    "rate_limiting_enabled",
                ]:
                    config[config_key] = env_value.lower() in ("true", "1", "yes", "on")
                elif config_key in [
                    "redis_max_connections",
                    "llm_timeout_seconds",
                    "api_request_timeout_seconds",
                    "cache_ttl_seconds",
                ]:
                    try:
                        config[config_key] = int(env_value)
                    except ValueError:
                        logger.warning(f"Invalid integer value for {env_var}: {env_value}")
                elif config_key == "default_temperature":
                    try:
                        config[config_key] = float(env_value)
                    except ValueError:
                        logger.warning(f"Invalid float value for {env_var}: {env_value}")
                else:
                    config[config_key] = env_value

        return config

    def load_config(self, environment: str | None = None) -> EnvironmentConfig:
        """Load complete configuration for the specified environment."""
        if self._loaded_config and environment is None:
            return self._loaded_config

        env = environment or self.environment

        # Load base configuration
        config_data = {}

        # Try to load environment-specific config
        env_config = self._load_yaml_config(env)
        config_data.update(env_config)

        # Merge with environment variables
        config_data = self._merge_with_env_vars(config_data)

        # Create and validate configuration
        try:
            config = EnvironmentConfig(**config_data)
            logger.info(f"Configuration loaded for environment: {env}")

            if environment is None:
                self._loaded_config = config

            return config
        except Exception as e:
            logger.error(f"Failed to create configuration: {e}")
            # Return default configuration on error
            return EnvironmentConfig()

    def get_environment(self) -> str:
        """Get current environment name."""
        return self.environment

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == "testing"


# Global configuration loader
_config_loader = ConfigLoader()


def get_environment_config() -> EnvironmentConfig:
    """Get current environment configuration."""
    return _config_loader.load_config()


def get_environment() -> str:
    """Get current environment name."""
    return _config_loader.get_environment()


def is_development() -> bool:
    """Check if running in development environment."""
    return _config_loader.is_development()


def is_production() -> bool:
    """Check if running in production environment."""
    return _config_loader.is_production()


def is_testing() -> bool:
    """Check if running in testing environment."""
    return _config_loader.is_testing()


def reload_config(environment: str | None = None) -> EnvironmentConfig:
    """Reload configuration (useful for testing)."""
    _config_loader._loaded_config = None
    return _config_loader.load_config(environment)
