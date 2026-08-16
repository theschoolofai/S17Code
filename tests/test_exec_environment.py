"""The sandboxed environment has to be small *and* viable.

`run_command` deliberately builds a minimal environment rather than inheriting
the parent's — that is the right instinct, and it is why an allowlisted command
cannot pick up credentials from the shell that started the server.

But a subprocess environment can be too small to run anything. On Windows,
Winsock and the DLL search path are resolved through `SystemRoot`; without it,
`import asyncio` raises `OSError: [WinError 10106]` before any user code runs.
pytest imports asyncio, so every verification command exits non-zero with a
stack trace that mentions neither the tests nor the change under test.

That failure mode is worse than a crash. `run_command` is the judge, so the
agent reads the result as "my edit broke the tests" and starts undoing correct
work to satisfy a test run that never actually happened.
"""
from __future__ import annotations

import sys

import pytest

from s17code.coding.exec import run_command


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("S17_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("S17_ALLOWED_COMMANDS", "python,git,pytest")
    from s17code.coding.workspace import Workspace

    return Workspace.from_env()


def test_a_command_can_import_asyncio(workspace):
    """The standard library must be usable inside the sandbox.

    Written as a script rather than `python -c`, because `-c` is refused as an
    unbounded shell — correctly.
    """
    (workspace.root / "probe.py").write_text("import asyncio\nprint('ok')\n")

    result = run_command(workspace, "python probe.py")

    assert result.exit_code == 0, (
        f"the sandbox environment cannot import asyncio:\n{result.stderr}"
    )
    assert "ok" in result.stdout


def test_a_command_can_open_a_socket(workspace):
    """Anything that binds a port — a test server, a live check — needs this."""
    (workspace.root / "probe.py").write_text(
        "import socket\n"
        "s = socket.socket()\n"
        "s.bind(('127.0.0.1', 0))\n"
        "print('bound', s.getsockname()[1] > 0)\n"
        "s.close()\n"
    )

    result = run_command(workspace, "python probe.py")

    assert result.exit_code == 0, result.stderr
    assert "bound True" in result.stdout


def test_the_environment_stays_minimal(workspace):
    """Fixing the above must not turn into inheriting the parent environment.

    The point of building the environment by hand is that a secret in the
    operator's shell does not reach an allowlisted command. A fix that passes
    `os.environ` through would make every test here pass and remove the property
    they exist to protect.
    """
    (workspace.root / "probe.py").write_text(
        "import os\nprint('\\n'.join(sorted(os.environ)))\n"
    )

    result = run_command(workspace, "python probe.py")
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    assert result.exit_code == 0, result.stderr
    assert "S17_CONTROL_TOKEN" not in names
    assert "GEMINI_API_KEY_1" not in names
    # A handful of platform essentials, not an inherited environment.
    assert len(names) <= 16, f"environment is no longer minimal: {sorted(names)}"


@pytest.mark.skipif(sys.platform != "win32", reason="SystemRoot is Windows-only")
def test_windows_essentials_are_present(workspace):
    (workspace.root / "probe.py").write_text(
        "import os\nprint(os.environ.get('SystemRoot', 'MISSING'))\n"
    )

    result = run_command(workspace, "python probe.py")

    assert result.exit_code == 0, result.stderr
    assert "MISSING" not in result.stdout
