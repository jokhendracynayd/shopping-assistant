import asyncio
import logging
import os
from collections.abc import AsyncIterator

from langchain_groq import ChatGroq  # Groq exposes OpenAI-compatible API

from app.config import settings

from .base import BaseLLMClient

logger = logging.getLogger(__name__)


class GroqClient(BaseLLMClient):
    """Wrapper for Groq LLMs (OpenAI-compatible)."""

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
            raise TimeoutError(f"LLM request timed out after {timeout} seconds") from None

    async def agenerate(self, prompt: str, **kwargs) -> str:

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = await asyncio.wait_for(self.llm.ainvoke(prompt, **kwargs), timeout=timeout)
            return response.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds") from None

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:

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
            raise TimeoutError(f"LLM request timed out after {timeout} seconds") from None

    async def achat(self, messages: list[dict[str, str]], **kwargs) -> str:

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            response = await asyncio.wait_for(self.llm.ainvoke(messages, **kwargs), timeout=timeout)
            return response.content
        except TimeoutError:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds") from None

    async def astream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream text generation asynchronously, yielding chunks as they arrive."""

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            # Create async generator with timeout
            async def stream_with_timeout():
                stream = self.llm.astream(prompt, **kwargs)
                async for chunk in stream:
                    if hasattr(chunk, "content") and chunk.content:
                        yield chunk.content
                    elif isinstance(chunk, str):
                        yield chunk

            # Wrap the streaming in a timeout
            start_time = asyncio.get_event_loop().time()
            async for chunk in stream_with_timeout():
                # Check timeout on each chunk
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"LLM stream timed out after {timeout} seconds")
                yield chunk

        except TimeoutError:
            raise TimeoutError(f"LLM stream timed out after {timeout} seconds") from None
        except Exception:
            logger.exception("Error in stream generation")
            raise

    async def achat_stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncIterator[str]:
        """Stream chat-based generation asynchronously, yielding chunks as they arrive."""

        timeout = kwargs.pop("timeout", settings.llm_timeout_seconds)

        try:
            # Create async generator with timeout
            async def stream_with_timeout():
                stream = self.llm.astream(messages, **kwargs)
                async for chunk in stream:
                    if hasattr(chunk, "content") and chunk.content:
                        yield chunk.content
                    elif isinstance(chunk, str):
                        yield chunk

            # Wrap the streaming in a timeout
            start_time = asyncio.get_event_loop().time()
            async for chunk in stream_with_timeout():
                # Check timeout on each chunk
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"LLM stream timed out after {timeout} seconds")
                yield chunk

        except TimeoutError:
            raise TimeoutError(f"LLM chat stream timed out after {timeout} seconds") from None
        except Exception:
            logger.exception("Error in chat stream generation")
            raise
