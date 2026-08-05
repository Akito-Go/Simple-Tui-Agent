"""配置管理测试 — 优先级、默认值、环境变量"""

import os
from pathlib import Path

import pytest
import yaml

from tui_agent.config.loader import _deep_merge, load_config, get_api_key
from tui_agent.config.schema import AppConfig, LLMConfig


class TestDeepMerge:
    def test_override_simple_value(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_merge_nested_dict(self):
        base = {"llm": {"model": "gpt-4o", "timeout": 120}}
        override = {"llm": {"model": "gpt-4o-mini"}}
        result = _deep_merge(base, override)
        assert result == {"llm": {"model": "gpt-4o-mini", "timeout": 120}}

    def test_add_new_key(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}


class TestLoadConfig:
    def test_default_config(self, tmp_path, monkeypatch):
        """无自定义配置时使用默认值"""
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")
        monkeypatch.chdir(tmp_path)
        config = load_config(project_root=tmp_path)
        assert isinstance(config, AppConfig)
        assert config.max_turns == 50
        assert config.llm.model == "gpt-4o-mini"

    def test_project_config_overrides_user(self, tmp_path, monkeypatch):
        """项目级配置覆盖用户级"""
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        # 创建用户级配置
        user_config = tmp_path / "user" / ".tui-agent.yaml"
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text(yaml.dump({"max_turns": 30, "llm": {"model": "gpt-4o"}}))

        # 创建项目级配置
        project_config = tmp_path / "project" / ".tui-agent.yaml"
        project_config.parent.mkdir(parents=True, exist_ok=True)
        project_config.write_text(yaml.dump({"llm": {"model": "gpt-4o-mini"}}))

        monkeypatch.setattr(Path, "home", lambda: user_config.parent)
        config = load_config(project_root=project_config.parent)

        # 项目级 model 覆盖用户级
        assert config.llm.model == "gpt-4o-mini"
        # 用户级 max_turns 覆盖默认 (项目级未设置)
        assert config.max_turns == 30

    def test_user_config_overrides_default(self, tmp_path, monkeypatch):
        """用户级配置覆盖默认值"""
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        user_config = tmp_path / "user" / ".tui-agent.yaml"
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text(yaml.dump({"max_turns": 10}))

        monkeypatch.setattr(Path, "home", lambda: user_config.parent)
        config = load_config(project_root=tmp_path)

        assert config.max_turns == 10
        # 未覆盖的保持默认
        assert config.llm.model == "gpt-4o-mini"


class TestApiKey:
    def test_get_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test123")
        assert get_api_key() == "sk-test123"

    def test_get_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("TUI_AGENT_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="TUI_AGENT_API_KEY"):
            get_api_key()

    def test_get_anthropic_api_key(self, monkeypatch):
        monkeypatch.delenv("TUI_AGENT_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        assert get_api_key("anthropic") == "sk-ant-test"

    def test_get_api_key_from_dotenv(self, tmp_path, monkeypatch):
        """测试从 .env 文件读取 API Key"""
        monkeypatch.delenv("TUI_AGENT_API_KEY", raising=False)

        # 创建 .env 文件
        env_file = tmp_path / ".env"
        env_file.write_text("TUI_AGENT_API_KEY=sk-from-dotenv\n")

        # 加载配置（会触发 _load_dotenv）
        config = load_config(project_root=tmp_path)
        assert get_api_key() == "sk-from-dotenv"

    def test_env_override_dotenv(self, tmp_path, monkeypatch):
        """测试环境变量优先于 .env 文件"""
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-from-env")

        # 创建 .env 文件（不应覆盖环境变量）
        env_file = tmp_path / ".env"
        env_file.write_text("TUI_AGENT_API_KEY=sk-from-dotenv\n")

        config = load_config(project_root=tmp_path)
        assert get_api_key() == "sk-from-env"

    def test_dotenv_with_comments(self, tmp_path, monkeypatch):
        """测试 .env 文件中的注释和空行"""
        monkeypatch.delenv("TUI_AGENT_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("""
# 这是注释
TUI_AGENT_API_KEY=sk-after-comment

# 另一个注释
""")

        config = load_config(project_root=tmp_path)
        assert get_api_key() == "sk-after-comment"


class TestDotenvConfig:
    def test_dotenv_model_override(self, tmp_path, monkeypatch):
        """测试 .env 中的模型配置覆盖默认值"""
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
TUI_AGENT_MAX_TURNS=10
""")

        config = load_config(project_root=tmp_path)
        assert config.llm.model == "gpt-4o-mini"
        assert config.max_turns == 10

    def test_dotenv_partial_override(self, tmp_path, monkeypatch):
        """测试 .env 部分覆盖，未设置的保持默认值"""
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
""")

        config = load_config(project_root=tmp_path)
        assert config.llm.model == "gpt-4o-mini"
        # 未设置的保持默认值
        assert config.llm.timeout == 120
        assert config.max_turns == 50

    def test_dotenv_full_config(self, tmp_path, monkeypatch):
        """测试 .env 完整配置"""
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
TUI_AGENT_API_BASE=https://custom.api.com/v1
TUI_AGENT_TIMEOUT=60
TUI_AGENT_MAX_TURNS=5
TUI_AGENT_MAX_RETRIES=1
""")

        config = load_config(project_root=tmp_path)
        assert config.llm.model == "gpt-4o-mini"
        assert config.llm.api_base == "https://custom.api.com/v1"
        assert config.llm.timeout == 60
        assert config.llm.max_retries == 1
        assert config.max_turns == 5

    def test_dotenv_override_yaml(self, tmp_path, monkeypatch):
        """测试 .env 配置覆盖 YAML 配置"""
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        # 创建项目级 YAML 配置
        yaml_config = tmp_path / ".tui-agent.yaml"
        yaml_config.write_text(yaml.dump({
            "llm": {"model": "gpt-4o", "timeout": 200},
            "max_turns": 30,
        }))

        # 创建 .env 覆盖（仅覆盖 model）
        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
""")

        config = load_config(project_root=tmp_path)
        # .env 覆盖 YAML 的 model
        assert config.llm.model == "gpt-4o-mini"
        # YAML 的 timeout 未被 .env 覆盖，保持 YAML 值
        assert config.llm.timeout == 200
        # YAML 的 max_turns 未被 .env 覆盖，保持 YAML 值
        assert config.max_turns == 30


class TestAvailableModels:
    def test_available_models_from_env_comma_separated(self, tmp_path, monkeypatch):
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
TUI_AGENT_MODELS=moonshot/kimi-k2.5,gpt-4o-mini,xiaomi/mimo-v2.5-pro
""")

        config = load_config(project_root=tmp_path)
        assert config.available_models == [
            "moonshot/kimi-k2.5",
            "gpt-4o-mini",
            "xiaomi/mimo-v2.5-pro",
        ]

    def test_available_models_from_env_multiline_block(self, tmp_path, monkeypatch):
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=gpt-4o-mini
TUI_AGENT_MODELS=[
moonshot/kimi-k2.5
deepseek/deepseek-v4-pro
gpt-4o-mini
xiaomi/mimo-v2.5-pro
]
""")

        config = load_config(project_root=tmp_path)
        assert config.available_models == [
            "moonshot/kimi-k2.5",
            "deepseek/deepseek-v4-pro",
            "gpt-4o-mini",
            "xiaomi/mimo-v2.5-pro",
        ]

    def test_current_model_appended_if_missing_from_list(self, tmp_path, monkeypatch):
        _clear_agent_env(monkeypatch)
        monkeypatch.setenv("TUI_AGENT_API_KEY", "sk-test")

        env_file = tmp_path / ".env"
        env_file.write_text("""
TUI_AGENT_API_KEY=sk-test
TUI_AGENT_MODEL=custom/model
TUI_AGENT_MODELS=moonshot/kimi-k2.5,xiaomi/mimo-v2.5-pro
""")

        config = load_config(project_root=tmp_path)
        assert config.available_models[0] == "custom/model"


def _clear_agent_env(monkeypatch):
    """清除所有 TUI Agent 相关环境变量"""
    for key in (
        "TUI_AGENT_MODEL",
        "TUI_AGENT_MODELS",
        "TUI_AGENT_API_BASE",
        "TUI_AGENT_TIMEOUT",
        "TUI_AGENT_MAX_TURNS",
        "TUI_AGENT_MAX_RETRIES",
    ):
        monkeypatch.delenv(key, raising=False)
