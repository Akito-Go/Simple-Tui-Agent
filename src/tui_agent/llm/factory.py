"""LLM Provider 工厂 — 按配置创建 OpenAI 兼容或 Anthropic Provider"""

from ..config.schema import LLMConfig
from .openai_compat import OpenAICompatProvider
from .provider import LLMProvider

OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com"


def normalize_provider_name(provider: str) -> str:
    name = (provider or "openai_compat").strip().lower()
    if name in ("openai", "openai_compat"):
        return "openai_compat"
    if name in ("anthropic", "claude"):
        return "anthropic"
    return name


def infer_provider_for_model(model: str) -> str | None:
    """根据模型名推断 provider；无法判断时返回 None（保持当前）。"""
    m = (model or "").strip().lower()
    if not m:
        return None
    if m.startswith("claude") or "anthropic" in m:
        return "anthropic"
    if m.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
        return "openai_compat"
    return None


def apply_provider_defaults(llm: LLMConfig, provider: str) -> None:
    """切换 provider 时校正默认 api_base。"""
    name = normalize_provider_name(provider)
    llm.provider = name
    base = llm.api_base or ""
    if name == "anthropic":
        if not base or "openai.com" in base:
            llm.api_base = ANTHROPIC_DEFAULT_BASE
    else:
        if not base or "anthropic.com" in base:
            llm.api_base = OPENAI_DEFAULT_BASE


def create_llm_provider(llm: LLMConfig, api_key: str) -> LLMProvider:
    """
    根据 llm.provider 创建对应实现。

    支持:
      - openai / openai_compat（默认）
      - anthropic / claude
    """
    name = normalize_provider_name(llm.provider)

    if name == "openai_compat":
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=llm.api_base or OPENAI_DEFAULT_BASE,
            model=llm.model,
            timeout=llm.timeout,
            max_retries=llm.max_retries,
        )

    if name == "anthropic":
        try:
            from .anthropic_compat import AnthropicProvider
        except ImportError as e:
            raise ValueError(
                "使用 Anthropic 需要安装 anthropic 包: pip install anthropic\n"
                "或在项目虚拟环境中执行: pip install -e \".[dev]\""
            ) from e

        base = llm.api_base or ANTHROPIC_DEFAULT_BASE
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
