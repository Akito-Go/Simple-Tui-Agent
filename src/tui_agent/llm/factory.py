"""LLM Provider 工厂 — 按配置创建 OpenAI 兼容或 Anthropic Provider"""

from ..config.schema import LLMConfig
from .anthropic_compat import ANTHROPIC_DEFAULT_BASE, AnthropicProvider
from .openai_compat import OpenAICompatProvider
from .provider import LLMProvider

OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"


def create_llm_provider(llm: LLMConfig, api_key: str) -> LLMProvider:
    """
    根据 llm.provider 创建对应实现。

    支持:
      - openai / openai_compat（默认）
      - anthropic / claude
    """
    name = (llm.provider or "openai_compat").strip().lower()

    if name in ("openai", "openai_compat"):
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=llm.api_base or OPENAI_DEFAULT_BASE,
            model=llm.model,
            timeout=llm.timeout,
            max_retries=llm.max_retries,
        )

    if name in ("anthropic", "claude"):
        base = llm.api_base or ANTHROPIC_DEFAULT_BASE
        # 避免沿用 OpenAI 默认 base
        if "openai.com" in base:
            base = ANTHROPIC_DEFAULT_BASE
        return AnthropicProvider(
            api_key=api_key,
            base_url=base,
            model=llm.model,
            timeout=llm.timeout,
            max_retries=llm.max_retries,
        )

    raise ValueError(
        f"未知 LLM provider: {llm.provider!r}。"
        f"支持: openai_compat, anthropic"
    )
