"""Tests for logging alongside machine-readable status output."""

import json
import subprocess
import sys


def test_default_logging_keeps_stdout_machine_readable() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, logging; "
            "from mmtools.arguments import setup_logging; "
            "setup_logging('warning'); "
            "logging.warning('connection interrupted'); "
            "print(json.dumps({'text': 'MM', 'class': 'other'}))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"text": "MM", "class": "other"}
    assert "connection interrupted" in result.stderr
