"""HOME is the workspace, so `.gitconfig` is git's global config — a shell.

Not the `.git/hooks` PR: that injects `core.hooksPath=` and protects `.git/**`.
`git status` still honours `core.fsmonitor` and `git diff` honours `diff.external`
from `$HOME/.gitconfig`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from s17code.coding import GuardError, Workspace, run_command
from s17code.coding.edit import EditLedger, create_file
from s17code.coding.guard import is_protected


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    (tmp_path / "calc.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return Workspace.open(tmp_path)


def test_gitconfig_is_not_the_work(repo) -> None:
    assert is_protected(".gitconfig") == ".gitconfig"
    assert is_protected(".config/git/config") == ".config/git/**"
    with pytest.raises(GuardError, match="protected pattern"):
        create_file(
            repo, EditLedger(), ".gitconfig",
            content="[core]\n\tfsmonitor = /bin/touch pwned\n",
        )


def test_git_status_does_not_run_a_planted_fsmonitor(repo) -> None:
    """Defense in depth: a config that already exists must not execute."""
    (repo.root / ".gitconfig").write_text(
        "[core]\n\tfsmonitor = /bin/touch fsmonitor-pwned\n",
        encoding="utf-8",
    )
    (repo.root / "calc.py").write_text("x = 2\n", encoding="utf-8")
    result = run_command(repo, ["git", "status", "--porcelain"], timeout=20)
    assert result.ok
    assert not (repo.root / "fsmonitor-pwned").exists()


def test_git_diff_does_not_run_a_planted_external_diff(repo) -> None:
    (repo.root / ".gitconfig").write_text(
        "[diff]\n\texternal = /bin/touch diff-pwned\n",
        encoding="utf-8",
    )
    (repo.root / "calc.py").write_text("x = 2\n", encoding="utf-8")
    result = run_command(repo, ["git", "diff"], timeout=20)
    assert result.ok
    assert not (repo.root / "diff-pwned").exists()
