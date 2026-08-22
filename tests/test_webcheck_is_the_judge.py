"""webcheck.js is the JS judge, the same way tests/ is the Python judge.

Not S17Code #12: that PR left package.json writable on purpose (`npm run`).
webcheck.js is the harness Kiln and skills/web-pages tell the agent to satisfy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from s17code.coding import GuardError, Workspace
from s17code.coding.edit import EditLedger, apply_edit, create_file
from s17code.coding.guard import is_protected


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    (tmp_path / "index.html").write_text("<html></html>\n")
    (tmp_path / "webcheck.js").write_text("process.exit(1)\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return Workspace.open(tmp_path)


def test_webcheck_js_is_the_judge_not_the_work(repo) -> None:
    assert is_protected("webcheck.js") == "webcheck.js"
    assert is_protected("pages/webcheck.js") == "**/webcheck.js"
    assert is_protected("index.html") is None
    assert is_protected("package.json") is None
    ledger = EditLedger()
    ledger.record_read("webcheck.js")
    with pytest.raises(GuardError, match="protected pattern"):
        apply_edit(repo, ledger, "webcheck.js",
                   old_string="process.exit(1)", new_string="process.exit(0)")
    with pytest.raises(GuardError, match="protected pattern"):
        create_file(repo, EditLedger(), "nested/webcheck.js",
                    content="process.exit(0)\n")
