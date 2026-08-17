from __future__ import annotations

import os
from pathlib import Path

import pytest

CONTROL_TOKEN = "test-control-token"
COMPLETION_TOKEN = "test-completion-token"


@pytest.fixture(autouse=True, scope="session")
def _ignore_the_developers_dotenv():
    """Assert the code's defaults, never one machine's .env.

    ``s17code.main`` calls ``load_dotenv()`` at import time, before its own
    submodule imports, so the first test that builds the app injects that
    developer's configuration into ``os.environ`` for the rest of the session.
    Everything ordered after it then reads their settings instead of the
    defaults, which is how the same suite produced different failures on the
    same commit depending only on whether a ``.env`` existed.

    That matters most for the guard. ``test_coding_surface`` proves the agent
    cannot edit the thing that grades it, and it reads ``S17_PROTECTED_PATHS``
    at call time — so with a ``.env`` present it asserts whatever that developer
    happened to configure rather than ``DEFAULT_PROTECTED``.

    Trigger the import here, then drop every key the file introduced.
    """
    from dotenv import dotenv_values

    env_file = Path(__file__).resolve().parents[1] / ".env"
    injected = set(dotenv_values(env_file)) if env_file.exists() else set()

    import s17code.main  # noqa: F401  - for its import-time load_dotenv

    for key in injected:
        os.environ.pop(key, None)
    yield


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("S17_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("S17_A2A_GRPC_ENABLED", "0")
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path / "sandbox"))
    # The control plane fails closed. Tests configure a token exactly as a real
    # deployment must; they do not get a bypass, so the gates stay exercised
    # rather than disabled for convenience.
    monkeypatch.setenv("S17_CONTROL_TOKEN", CONTROL_TOKEN)
    monkeypatch.setenv("S17_COMPLETION_TOKEN", COMPLETION_TOKEN)
    (tmp_path / "sandbox").mkdir()


@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient

    from s17code.main import app

    with TestClient(app, headers={"Authorization": f"Bearer {CONTROL_TOKEN}"}) as client:
        yield client
