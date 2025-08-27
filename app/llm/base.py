from abc import ABC
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    All providers (OpenAI, Groq, Anthropic) must implement this interface.
    """

    def __init__(self, api_key: str | None, model_name: str, temperature: float = 0.0):
        """Initialize client.

        Do NOT raise on missing API key here to allow tests/mocks. Validation of credentials should
        happen at startup or via an explicit `validate()` call so unit tests can construct clients
        without keys.
        """
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature

    @abstractmethod
    def get_model(self, **kwargs) -> Any:
        """Return an initialized LLM model instance."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Run text generation given a prompt (synchronous)"""

    @abstractmethod
    async def agenerate(self, prompt: str, **kwargs) -> str:
        """Run text generation asynchronously."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Run a chat-based generation with conversation history."""

    @abstractmethod
    async def achat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Async chat interface."""

    @abstractmethod
    async def astream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream text generation asynchronously, yielding chunks as they arrive."""

    @abstractmethod
    async def achat_stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncIterator[str]:
        """Stream chat-based generation asynchronously, yielding chunks as they arrive."""

    def generate_structured(self, prompt: str, schema: type[BaseModel], **kwargs) -> BaseModel:
        """Run structured output generation based on a Pydantic schema.

        Providers with JSON-mode (like OpenAI/Anthropic) should override.
        """
        raw = self.generate(prompt, **kwargs)
        return schema.model_validate_json(raw)

    def is_configured(self) -> bool:
        """Return True when the client has required credentials configured."""
        return bool(self.api_key)

    def validate(self) -> None:
        """Validate client configuration and raise a clear error if missing.

        Call this during application startup to fail fast on missing credentials.
        """
        if not self.is_configured():
            raise ValueError(
                f"LLM client {self.__class__.__name__} is not configured with an API key"
            )
