from langchain_openai import ChatOpenAI

from app.config import settings

from .base import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    """Wrapper around LangChain's OpenAI LLM client.

    Supports structured outputs via JSON mode.
    """

    def __init__(
        self, model_name: str = "gpt-4o-mini", temperature: float = settings.default_temperature
    ):
        super().__init__(
            api_key=settings.OPENAI_API_KEY, model_name=model_name, temperature=temperature
        )
        self.llm = self.get_model()

    def get_model(self, **kwargs) -> ChatOpenAI:
        return ChatOpenAI(model=self.model_name, temperature=self.temperature, **kwargs)

    def generate(self, prompt: str, **kwargs) -> str:
        response = self.llm.invoke(prompt, **kwargs)
        return response.content

    async def agenerate(self, prompt: str, **kwargs) -> str:
        response = await self.llm.ainvoke(prompt, **kwargs)
        return response.content

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        response = self.llm.invoke(messages, **kwargs)
        return response.content

    async def achat(self, messages: list[dict[str, str]], **kwargs) -> str:
        response = await self.llm.ainvoke(messages, **kwargs)
        return response.content
