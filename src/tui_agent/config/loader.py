"""配置加载器 — 三级优先级：项目级 > 用户级 > 默认"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .schema import AppConfig, DEFAULT_AVAILABLE_MODELS, LLMConfig


def _parse_models_list(raw: str) -> list[str]:
    """解析逗号分隔的模型列表"""
    return [model.strip() for model in raw.split(",") if model.strip()]


def _normalize_model_entry(line: str) -> str | None:
    """解析方括号列表中的单行模型名"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("- "):
        line = line[2:].strip()
    return line.strip(",").strip().strip('"').strip("'") or None


def _read_models_from_dotenv(env_path: Path) -> list[str] | None:
    """
    从 .env 读取 TUI_AGENT_MODELS，支持两种格式：

    1. 多行列表（推荐）:
       TUI_AGENT_MODELS=[
       gpt-4o-mini
       gpt-4o
       ]

    2. 单行逗号分隔:
       TUI_AGENT_MODELS=gpt-4o-mini,gpt-4o
    """
    if not env_path.exists():
        return None

    content = env_path.read_text(encoding="utf-8")

    block_match = re.search(
        r"^TUI_AGENT_MODELS\s*=\s*\[(.*?)^\]",
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    if block_match:
        models = []
        for line in block_match.group(1).splitlines():
            model = _normalize_model_entry(line)
            if model:
                models.append(model)
        return models or None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("TUI_AGENT_MODELS="):
            value = stripped.split("=", 1)[1].strip()
            if value == "[":
                continue
            value = value.strip('"').strip("'")
            if value:
                return _parse_models_list(value)
    return None


def _load_dotenv(project_root: Path) -> None:
    """加载 .env 文件中的环境变量（不覆盖已存在的环境变量）"""
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    in_models_block = False
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if in_models_block:
                if stripped.endswith("]"):
                    in_models_block = False
                continue
            if stripped.startswith("TUI_AGENT_MODELS=") and stripped.rstrip().endswith("["):
                in_models_block = True
                continue
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, value = stripped.partition("=")
                key = key.strip()
                if key == "TUI_AGENT_MODELS":
                    continue
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    """加载 YAML 文件，文件不存在返回空字典"""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_LLM_FLAT_KEYS = ("provider", "model", "api_base", "timeout", "max_retries")


def _get_default_config() -> dict[str, Any]:
    """获取内置默认配置"""
    default_path = Path(__file__).parent.parent.parent.parent / "config" / "default.yaml"
    return _load_yaml(default_path)


def _normalize_llm_section(config_dict: dict[str, Any]) -> dict[str, Any]:
    """将顶层 LLM 字段并入 llm: 块（兼容旧 YAML 扁平写法）"""
    llm = dict(config_dict.get("llm") or {})
    for key in _LLM_FLAT_KEYS:
        if key in config_dict and key not in llm:
            llm[key] = config_dict[key]
    config_dict = dict(config_dict)
    config_dict["llm"] = llm
    return config_dict


def load_config(project_root: Path | None = None) -> AppConfig:
    """
    加载配置，优先级：.env 环境变量 > 项目级 YAML > 用户级 YAML > 默认

    - .env: <project_root>/.env (环境变量方式，最高优先级)
    - 项目级: <project_root>/.tui-agent.yaml
    - 用户级: ~/.tui-agent.yaml
    - 默认: config/default.yaml (内置)

    支持通过 .env 文件统一配置所有运行环境变量：
      TUI_AGENT_API_KEY=sk-xxx     # API Key（OpenAI 兼容）
      ANTHROPIC_API_KEY=sk-ant-... # Anthropic（provider=anthropic 时）
      TUI_AGENT_PROVIDER=openai_compat|anthropic
      TUI_AGENT_MODEL=gpt-4o-mini
      TUI_AGENT_MODELS=[...]
      TUI_AGENT_API_BASE=...
      TUI_AGENT_TIMEOUT=120
      TUI_AGENT_MAX_TURNS=20
      TUI_AGENT_MAX_RETRIES=3
    """
    if project_root is None:
        project_root = Path.cwd()

    # 0. 加载 .env 文件（不覆盖已有环境变量）
    _load_dotenv(project_root)

    # 1. 加载默认配置
    config_dict = _get_default_config()

    # 2. 合并用户级配置
    user_config_path = Path.home() / ".tui-agent.yaml"
    user_config = _load_yaml(user_config_path)
    config_dict = _deep_merge(config_dict, user_config)

    # 3. 合并项目级配置
    project_config_path = project_root / ".tui-agent.yaml"
    project_config = _load_yaml(project_config_path)
    config_dict = _deep_merge(config_dict, project_config)

    # 3.5 规范化 llm 段（兼容顶层扁平字段）
    config_dict = _normalize_llm_section(config_dict)

    # 4. .env 环境变量覆盖（最高优先级）
    env_overrides = {
        "provider": os.environ.get("TUI_AGENT_PROVIDER"),
        "model": os.environ.get("TUI_AGENT_MODEL"),
        "api_base": os.environ.get("TUI_AGENT_API_BASE"),
        "timeout": os.environ.get("TUI_AGENT_TIMEOUT"),
        "max_retries": os.environ.get("TUI_AGENT_MAX_RETRIES"),
    }
    llm_dict = dict(config_dict.get("llm") or {})
    for key, value in env_overrides.items():
        if value is not None:
            if key in ("timeout", "max_retries"):
                llm_dict[key] = int(value)
            else:
                llm_dict[key] = value

    max_turns_env = os.environ.get("TUI_AGENT_MAX_TURNS")
    max_turns = int(max_turns_env) if max_turns_env else config_dict.get("max_turns", 50)

    context_max_tokens_env = os.environ.get("TUI_AGENT_CONTEXT_MAX_TOKENS")
    context_max_tokens = int(context_max_tokens_env) if context_max_tokens_env else config_dict.get("context_max_tokens", 32000)

    env_path = project_root / ".env"
    models_from_dotenv = _read_models_from_dotenv(env_path)
    models_env = os.environ.get("TUI_AGENT_MODELS")
    if models_from_dotenv:
        available_models = models_from_dotenv
    elif models_env:
        available_models = _parse_models_list(models_env)
    else:
        available_models = config_dict.get("available_models") or []

    # 5. 构建配置模型
    llm_config = LLMConfig(**llm_dict)

    app_config = AppConfig(
        max_turns=max_turns,
        context_max_tokens=context_max_tokens,
        llm=llm_config,
        available_models=available_models or list(DEFAULT_AVAILABLE_MODELS),
    )
    if app_config.llm.model not in app_config.available_models:
        app_config.available_models.insert(0, app_config.llm.model)
    return app_config


def get_api_key(provider: str | None = None) -> str:
    """从环境变量获取 API Key（支持 .env 文件）"""
    name = (provider or "").strip().lower()
    if name in ("anthropic", "claude"):
        api_key = (
            os.environ.get("ANTHROPIC_API_KEY", "")
            or os.environ.get("TUI_AGENT_API_KEY", "")
        )
        if not api_key:
            raise ValueError(
                "未设置 ANTHROPIC_API_KEY（或 TUI_AGENT_API_KEY）。请通过以下方式之一配置:\n"
                "  1. 创建 .env 文件: echo 'ANTHROPIC_API_KEY=<your_key>' > .env\n"
                "  2. 设置环境变量: export ANTHROPIC_API_KEY=<your_key>\n"
                "  3. 并设置 TUI_AGENT_PROVIDER=anthropic"
            )
        return api_key

    api_key = (
        os.environ.get("TUI_AGENT_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    if not api_key:
        raise ValueError(
            "未设置 TUI_AGENT_API_KEY（或 OPENAI_API_KEY / ANTHROPIC_API_KEY）。请通过以下方式之一配置:\n"
            "  1. 创建 .env 文件: echo 'TUI_AGENT_API_KEY=<your_key>' > .env\n"
            "  2. 设置环境变量: export TUI_AGENT_API_KEY=<your_key>"
        )
    return api_key
