"""需要回环端口的 SDK 集成测试，通过 STA_TEST_LOCAL_HTTP=1 显式启用。"""

import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get("STA_TEST_LOCAL_HTTP") != "1", reason="requires loopback HTTP server")
@pytest.mark.parametrize("mode", ["finish", "early"])
def test_real_sdk_stream_shutdown(mode):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("stream_shutdown_probe.py")), mode],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "an error occurred during closing" not in result.stderr
