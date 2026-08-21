"""Allowlisted interpreters must not become shells through their eval flags."""
from __future__ import annotations

import pytest

from s17code.coding.exec import CommandError, _check


def test_node_eval_is_refused() -> None:
    with pytest.raises(CommandError):
        _check(["node", "-e", "require('child_process').execSync('id')"])


def test_node_long_eval_and_print_are_refused() -> None:
    with pytest.raises(CommandError):
        _check(["node", "--eval", "process.exit(0)"])
    with pytest.raises(CommandError):
        _check(["node", "-p", "process.version"])


def test_npm_script_execution_is_refused() -> None:
    with pytest.raises(CommandError):
        _check(["npm", "run", "build"])
    with pytest.raises(CommandError):
        _check(["npm", "exec", "--", "anything"])


def test_running_a_node_file_is_still_allowed() -> None:
    _check(["node", "scripts/check.js"])
    _check(["npm", "test"])
    _check(["python", "-m", "pytest", "-q"])