import subprocess
import sys


def test_cli_help_lists_non_interactive_options():
    result = subprocess.run([sys.executable, "-m", "tui_agent", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--prompt" in result.stdout and "--json" in result.stdout and "--yes" in result.stdout


def test_completion_candidates_include_commands_tools_and_models():
    from tests.test_tui_layout import LayoutApp
    app = LayoutApp()
    app.config = type("Config", (), {"available_models": ["demo-model"]})()
    app.agent_loop = type("Loop", (), {"tool_registry": type("Registry", (), {"_tools": {"read_file": object()}})()})()
    candidates = app.completion_candidates()
    assert "/plan" in candidates and "read_file" in candidates and "demo-model" in candidates
