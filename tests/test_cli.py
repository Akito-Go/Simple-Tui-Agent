import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252", "gbk"])
def test_cli_help_lists_non_interactive_options(encoding):
    result = subprocess.run(
        [sys.executable, "-m", "tui_agent", "--help"],
        capture_output=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": encoding},
    )
    assert result.returncode == 0, result.stderr
    assert "终端编码" in result.stdout
    assert "--prompt" in result.stdout and "--json" in result.stdout and "--yes" in result.stdout


def test_cli_error_output_is_utf8():
    result = subprocess.run(
        [sys.executable, "-m", "tui_agent", "--setup", "--json"],
        capture_output=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 2
    assert "不能与" in result.stderr
    assert "UnicodeEncodeError" not in result.stderr


def test_environment_changes_reach_child_process(monkeypatch):
    monkeypatch.setenv("STA_TEST_ENV_MARKER", "inherited")
    result = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ.get('STA_TEST_ENV_MARKER'))"],
        capture_output=True, encoding="utf-8", check=True,
    )
    assert result.stdout.strip() == "inherited"
    if os.name == "nt":
        assert os.environ["sta_test_env_marker"] == "inherited"


def test_completion_candidates_include_commands_tools_and_models():
    from tests.test_tui_layout import LayoutApp
    app = LayoutApp()
    app.config = type("Config", (), {"available_models": ["demo-model"]})()
    app.agent_loop = type("Loop", (), {"tool_registry": type("Registry", (), {"_tools": {"read_file": object()}})()})()
    candidates = app.completion_candidates()
    assert "/plan" in candidates and "read_file" in candidates and "demo-model" in candidates
