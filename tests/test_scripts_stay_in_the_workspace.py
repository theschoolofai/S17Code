"""python/node may run a file; that file must still be inside the workspace.

S17Code #12 is argv[0] as a path (`/tmp/attacker/python`). This is argv after
that: `python /tmp/evil.py` and `node /tmp/evil.js` while cwd stays put.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from s17code.coding import CommandError, Workspace, run_command


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    (tmp_path / "calc.py").write_text("print('ok')\n")
    (tmp_path / "webcheck.js").write_text("console.log('ok')\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return Workspace.open(tmp_path)


def test_python_cannot_run_a_script_outside_the_workspace(repo, tmp_path) -> None:
    outside = tmp_path.parent / "outside-evil.py"
    outside.write_text("open('pwned', 'w').write('x')\n", encoding="utf-8")
    with pytest.raises(CommandError, match="outside the workspace"):
        run_command(repo, ["python", str(outside)], timeout=10)
    assert not (repo.root / "pwned").exists()


def test_node_cannot_run_a_script_outside_the_workspace(repo, tmp_path) -> None:
    outside = tmp_path.parent / "outside-evil.js"
    outside.write_text("require('fs').writeFileSync('pwned', 'x')\n", encoding="utf-8")
    with pytest.raises(CommandError, match="outside the workspace"):
        run_command(repo, ["node", str(outside)], timeout=10)
    assert not (repo.root / "pwned").exists()


def test_python_a_workspace_file_still_runs(repo) -> None:
    result = run_command(repo, ["python", "calc.py"], timeout=20)
    assert result.ok
    assert "ok" in result.stdout
