
from typing import List, Dict
import os
import logging

from langchain_groq import ChatGroq  # Groq exposes OpenAI-compatible API
from .base import BaseLLMClient
from app.config import settings


logger = logging.getLogger(__name__)


class GroqClient(BaseLLMClient):
    """
    Wrapper for Groq LLMs (OpenAI-compatible).
    """

    def __init__(self, model_name: str = "llama3-8b-8192", temperature: float = settings.default_temperature):
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
        response = self.llm.invoke(prompt, **kwargs)
        return response.content

    async def agenerate(self, prompt: str, **kwargs) -> str:
        response = await self.llm.ainvoke(prompt, **kwargs)
        return response.content

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        response = self.llm.invoke(messages, **kwargs)
        return response.content

    async def achat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        response = await self.llm.ainvoke(messages, **kwargs)
        return response.content
