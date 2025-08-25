
from langchain_anthropic import ChatAnthropic

from app.config import settings

from .base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    """
    Wrapper around Anthropic's Claude models.
    """

    def __init__(
        self,
        model_name: str = "claude-3-opus-20240229",
        temperature: float = settings.default_temperature,
    ):
        super().__init__(
            api_key=settings.ANTHROPIC_API_KEY, model_name=model_name, temperature=temperature
        )
        self.llm = self.get_model()

    def get_model(self, **kwargs) -> ChatAnthropic:
        return ChatAnthropic(model=self.model_name, temperature=self.temperature, **kwargs)

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
