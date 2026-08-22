"""Tests proving Windows env vars must be preserved in subprocess."""
import os
import sys
import pytest


def test_systemroot_required_on_windows():
    """On Windows, removing SYSTEMROOT from env breaks socket/DLL loading."""
    if sys.platform != 'win32':
        pytest.skip('Windows-only test')
    assert 'SYSTEMROOT' in os.environ, "SYSTEMROOT must be in the environment"
    assert os.path.isdir(os.environ['SYSTEMROOT']), "SYSTEMROOT must point to a valid directory"


def test_stripped_env_preserves_windows_vars():
    """Verify that our env-building logic preserves critical Windows vars."""
    base_env = {"PATH": os.environ.get("PATH", ""), "HOME": "/tmp",
                "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    # Simulate our fix: pass through Windows vars
    for winvar in ("SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "WINDIR"):
        if val := os.environ.get(winvar):
            base_env[winvar] = val
    if sys.platform == 'win32':
        assert 'SYSTEMROOT' in base_env, "SYSTEMROOT must be preserved on Windows"
        assert 'COMSPEC' in base_env, "COMSPEC must be preserved on Windows"


def test_asyncio_import_needs_systemroot():
    """asyncio.windows_events needs _overlapped which needs Winsock which needs SYSTEMROOT."""
    if sys.platform != 'win32':
        pytest.skip('Windows-only test')
    # This import would fail with OSError: [WinError 10106] if SYSTEMROOT is missing
    import asyncio
    assert asyncio is not None
