"""The allowlist must bound behaviour, not just spelling.

`exec.py` promises there is no shell. It already refuses `python -c` by name,
calling it "an unbounded shell". The same escape existed through the other
allowlisted interpreter, through `python -m`, and through `argv[0]` itself,
because the allowlist is checked against the basename while the full path is
what gets executed.
"""
from __future__ import annotations

import pytest

from s17code.coding.exec import CommandError, _check


@pytest.mark.parametrize("argv", [
    ["node", "-e", 'require("child_process").execSync("whoami")'],
    ["node", "--eval", 'require("child_process").execSync("whoami")'],
    ["node", "-p", 'require("child_process").execSync("whoami")'],
    ["node", "--print", 'require("child_process").execSync("whoami")'],
])
def test_node_eval_is_a_shell_by_another_name(argv):
    """`node -e` is exactly what `python -c` is refused for.

    Verified out of band: `node -e 'require("child_process").execSync("whoami")'`
    prints the current user. None of the SHELL_METACHARACTERS appear in that
    payload, so the metacharacter screen never sees it.
    """
    with pytest.raises(CommandError, match="unbounded shell"):
        _check(argv)


@pytest.mark.parametrize("argv", [
    ["python", "-m", "pip", "install", "anything"],
    ["python3", "-m", "pip", "install", "anything"],
    ["python", "-m", "ensurepip"],
])
def test_python_m_does_not_reach_a_tool_left_off_the_allowlist(argv):
    """`pip` is deliberately absent from DEFAULT_ALLOWLIST. `-m` reached it anyway."""
    with pytest.raises(CommandError, match="pip"):
        _check(argv)


def test_npm_exec_runs_arbitrary_programs():
    with pytest.raises(CommandError, match="npm exec|arbitrary"):
        _check(["npm", "exec", "--", "whoami"])


@pytest.mark.parametrize("program", [
    "/tmp/attacker/python",
    "../../../python",
    r"C:\attacker\python",
    "./python",
])
def test_argv0_must_be_a_bare_program_name(program):
    """The allowlist compared `os.path.basename(argv[0])` and then ran argv[0].

    Anything whose final path component happens to match an allowlisted name was
    executed from wherever the caller pointed.
    """
    with pytest.raises(CommandError, match="bare command name|path"):
        _check([program, "x.py"])


def test_the_ordinary_commands_still_pass():
    """The bounds must not cost the agent its actual job."""
    _check(["pytest", "-q"])
    _check(["python", "-m", "pytest", "-q"])
    _check(["python", "stability_test.py"])
    _check(["node", "build.js"])
    _check(["npm", "test"])
    _check(["git", "status"])
    _check(["uv", "run", "pytest"])
