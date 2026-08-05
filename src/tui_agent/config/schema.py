"""配置模型定义 — pydantic 类型安全校验"""

from pydantic import BaseModel, Field

DEFAULT_MODEL = "gpt-4o-mini"

DEFAULT_AVAILABLE_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "deepseek-chat",
]


class LLMConfig(BaseModel):
    """LLM Provider 配置"""

    provider: str = Field(default="openai_compat", description="Provider 类型")
    model: str = Field(default=DEFAULT_MODEL, description="模型名称")
    api_base: str = Field(
        default="https://api.openai.com/v1", description="API 地址"
    )
    timeout: int = Field(default=120, ge=1, description="请求超时时间 (秒)")
    max_retries: int = Field(default=3, ge=0, le=10, description="最大重试次数")


class AppConfig(BaseModel):
    """应用配置"""

    max_turns: int = Field(default=50, ge=1, le=100, description="最大循环轮次")
    context_max_tokens: int = Field(default=32000, ge=1000, le=128000, description="上下文压缩 token 阈值")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    available_models: list[str] = Field(
        default_factory=lambda: list(DEFAULT_AVAILABLE_MODELS),
        description="可通过 /model 切换的模型列表",
    )
