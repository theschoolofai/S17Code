"""git --git-dir / --work-tree / -C leave the workspace even though cwd does not.

Not S17Code #18 (clean/stash) and not the hooksPath PR: those still run git
inside the workspace. This flag family retargets the repository itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from s17code.coding import CommandError, Workspace, run_command


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "calc.py").write_text("x = 1\n")
    _init_repo(ws)
    return Workspace.open(ws)


@pytest.fixture
def other_repo(tmp_path: Path) -> Path:
    other = tmp_path / "other"
    other.mkdir()
    (other / "secret.txt").write_text("outside the workspace\n")
    _init_repo(other)
    return other


def test_git_git_dir_cannot_read_another_repository(repo, other_repo) -> None:
    with pytest.raises(CommandError, match="leave the workspace"):
        run_command(
            repo,
            ["git", f"--git-dir={other_repo / '.git'}", "log", "-1", "--oneline"],
            timeout=10,
        )


def test_git_work_tree_is_refused(repo, other_repo) -> None:
    with pytest.raises(CommandError, match="leave the workspace"):
        run_command(repo, ["git", f"--work-tree={other_repo}", "status"], timeout=10)


def test_git_dash_c_path_is_refused(repo, other_repo) -> None:
    with pytest.raises(CommandError, match="leave the workspace"):
        run_command(repo, ["git", "-C", str(other_repo), "status"], timeout=10)


def test_git_status_inside_the_workspace_still_runs(repo) -> None:
    result = run_command(repo, ["git", "status", "--porcelain"], timeout=20)
    assert result.ok
