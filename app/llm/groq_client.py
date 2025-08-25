import logging
import os

from langchain_groq import ChatGroq  # Groq exposes OpenAI-compatible API

from app.config import settings

from .base import BaseLLMClient

logger = logging.getLogger(__name__)


class GroqClient(BaseLLMClient):
    """
    Wrapper for Groq LLMs (OpenAI-compatible).
    """

    def __init__(
        self, model_name: str = "llama3-8b-8192", temperature: float = settings.default_temperature
    ):
        # Ensure GROQ_API_KEY is available in environment for the Groq SDK
        api_key = settings.GROQ_API_KEY
        if api_key:
            os.environ.setdefault("GROQ_API_KEY", api_key)
            logger.info("Initializing GroqClient (api_key present, masked).")
        else:
            logger.warning("Initializing GroqClient without an API key configured.")

        super().__init__(api_key=api_key, model_name=model_name, temperature=temperature)
        self.llm = self.get_model()

    def get_model(self, **kwargs) -> ChatGroq:
        return ChatGroq(model=self.model_name, temperature=self.temperature, **kwargs)

    def generate(self, prompt: str, **kwargs) -> str:
        import asyncio

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = asyncio.wait_for(self.llm.ainvoke(prompt, **kwargs), timeout=timeout)
            # Run in event loop if available, otherwise create new one
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in an async context, this shouldn't be called
                    raise RuntimeError("Use agenerate in async context")
                result = loop.run_until_complete(response)
            except RuntimeError:
                result = asyncio.run(response)
            return result.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds")

    async def agenerate(self, prompt: str, **kwargs) -> str:
        import asyncio

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = await asyncio.wait_for(self.llm.ainvoke(prompt, **kwargs), timeout=timeout)
            return response.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds")

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        import asyncio

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = asyncio.wait_for(self.llm.ainvoke(messages, **kwargs), timeout=timeout)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    raise RuntimeError("Use achat in async context")
                result = loop.run_until_complete(response)
            except RuntimeError:
                result = asyncio.run(response)
            return result.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds")

    async def achat(self, messages: list[dict[str, str]], **kwargs) -> str:
        import asyncio

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = await asyncio.wait_for(self.llm.ainvoke(messages, **kwargs), timeout=timeout)
            return response.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds")
