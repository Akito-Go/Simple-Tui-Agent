"""安装后首次配置、跨工作区复用和取消行为。"""

import os
from pathlib import Path
import sys

import pytest
import yaml

from tui_agent.config.loader import get_api_key, load_config
from tui_agent.config.setup import run_setup


def answers(monkeypatch, values, key="test-key"):
    responses = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))
    monkeypatch.setattr("tui_agent.config.setup.getpass", lambda prompt: key)


def test_setup_reuses_credentials_across_projects(tmp_path, monkeypatch, capsys):
    answers(monkeypatch, ["1", "https://example.test/v1", "demo-model"])
    run_setup()
    another = tmp_path / "another-project"
    another.mkdir()
    monkeypatch.chdir(another)
    config = load_config()
    assert config.llm.model == "demo-model"
    assert config.llm.api_base == "https://example.test/v1"
    assert get_api_key(config.llm.provider) == "test-key"
    assert not list(another.iterdir())
    assert "test-key" not in capsys.readouterr().out
    if os.name != "nt":
        assert (Path.home() / ".tui-agent.yaml").stat().st_mode & 0o777 == 0o600
    (another / ".env").write_text("TUI_AGENT_API_KEY=project-key\n")
    load_config()
    assert get_api_key(config.llm.provider) == "project-key"
    monkeypatch.setenv("TUI_AGENT_API_KEY", "environment-key")
    assert get_api_key(config.llm.provider) == "environment-key"


def test_setup_preserves_other_config_and_provider_keys(monkeypatch):
    path = Path.home() / ".tui-agent.yaml"
    path.write_text(yaml.safe_dump({"max_turns": 7, "api_keys": {"openai_compat": "old-key"}}))
    answers(monkeypatch, ["2", "", ""], "anthropic-test-key")
    run_setup()
    config = load_config()
    assert config.max_turns == 7
    assert config.llm.provider == "anthropic"
    assert config.llm.api_base == "https://api.anthropic.com"
    assert get_api_key("anthropic") == "anthropic-test-key"
    assert get_api_key("openai_compat") == "old-key"
    answers(monkeypatch, ["", "", ""], "")
    run_setup()
    assert get_api_key("anthropic") == "anthropic-test-key"


def test_cancel_setup_keeps_existing_file(monkeypatch):
    path = Path.home() / ".tui-agent.yaml"
    original = "max_turns: 7\n"
    path.write_text(original)
    answers(monkeypatch, ["1", "", ""])

    def cancel(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("tui_agent.config.setup.getpass", cancel)
    with pytest.raises(KeyboardInterrupt):
        run_setup()
    assert path.read_text() == original


def test_invalid_url_reprompts(monkeypatch):
    answers(monkeypatch, ["wrong", "1", "invalid", "https://example.test/v1", "demo"])
    run_setup()
    assert load_config().llm.api_base == "https://example.test/v1"


def test_user_config_is_blocked_from_file_tools(tmp_path):
    from tui_agent.tools.sensitive_paths import check_sensitive_path

    assert check_sensitive_path(Path.home() / ".tui-agent.yaml")
    assert check_sensitive_path(tmp_path / ".tui-agent.yaml") is None


def test_first_launch_runs_setup_then_tui(monkeypatch):
    from tui_agent.__main__ import main

    answers(monkeypatch, ["1", "", ""])
    monkeypatch.setattr(sys, "argv", ["douhua"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    launched = []
    monkeypatch.setattr("tui_agent.tui.app.TuiAgentApp.run", lambda self: launched.append(True))
    main()
    assert launched == [True]
    assert get_api_key() == "test-key"
    # 再次启动不能重走向导（模拟输入已经耗尽）。
    main()
    assert launched == [True, True]


def test_non_terminal_launch_does_not_prompt(monkeypatch, capsys):
    from tui_agent.__main__ import main

    monkeypatch.setattr(sys, "argv", ["douhua"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "douhua --setup" in capsys.readouterr().err
    assert not (Path.home() / ".tui-agent.yaml").exists()
