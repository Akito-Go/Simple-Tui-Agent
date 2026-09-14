"""首次启动配置向导；配置保存在用户目录，工作区保持不变。"""

from getpass import getpass
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

import yaml

from .loader import _load_yaml, _normalize_llm_section
from .schema import LLMConfig


def run_setup() -> None:
    path = Path.home() / ".tui-agent.yaml"
    config = _normalize_llm_section(_load_yaml(path))
    previous = LLMConfig(**config["llm"])
    print("STA 配置向导 · Ctrl+C 取消")
    print("1. OpenAI 兼容服务（含第三方服务）\n2. Anthropic")
    default = "2" if previous.provider in ("anthropic", "claude") else "1"
    while True:
        choice = input(f"选择服务商 [{default}]: ").strip() or default
        if choice in ("1", "2"):
            break
        print("请输入 1 或 2。")
    provider = "anthropic" if choice == "2" else "openai_compat"
    same_provider = previous.provider in (
        ("anthropic", "claude") if choice == "2" else ("openai_compat", "openai")
    )
    base = previous.api_base if same_provider else "https://api.anthropic.com"
    model = previous.model if same_provider else "claude-sonnet-4-5"
    if not same_provider and choice == "1":
        base, model = "https://api.openai.com/v1", "gpt-4o-mini"
    while True:
        api_base = input(f"API 地址 [{base}]: ").strip() or base
        try:
            url = urlsplit(api_base)
            valid = url.scheme in ("http", "https") and url.hostname and not url.username and not url.password
        except ValueError:
            valid = False
        if valid:
            break
        print("请输入有效的 http:// 或 https:// 地址，不要在地址中包含密钥。")
    model = input(f"模型名称 [{model}]: ").strip() or model
    keys = dict(config.get("api_keys") or {})
    saved_key = keys.get(provider, "")
    print(f"配置与密钥将保存到 {path}，密钥以明文保存在本机，输入时不回显。")
    while True:
        key = getpass("API Key（留空保留已保存密钥）: " if saved_key else "API Key: ").strip()
        if key or saved_key:
            break
        print("API Key 不能为空。")
    config["llm"].update(provider=provider, api_base=api_base, model=model)
    keys[provider] = key or saved_key
    config["api_keys"] = keys

    # 临时文件从创建起仅当前用户可读写；所有输入完成后才替换原配置。
    fd, temporary = tempfile.mkstemp(prefix=".tui-agent-", suffix=".yaml", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("配置已保存。工作区配置和环境变量仍优先生效；可用 sta --setup 重新配置。")
