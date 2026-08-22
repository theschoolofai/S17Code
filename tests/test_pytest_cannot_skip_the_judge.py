"""pytest --ignore / --override-ini / -c make the suite green without the judge.

Not S17Code #12 (python -c / node -e) and not protecting tests/ from edit:
this is the runner skipping the suite that is still on disk.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from s17code.coding import CommandError, Workspace, run_command


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    (tmp_path / "tests").mkdir()
    (tmp_path / "calc.py").write_text("def average(xs):\n    return 1\n")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import average\n\ndef test_empty():\n    assert average([]) == 0\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return Workspace.open(tmp_path)


@pytest.mark.parametrize("command", [
    ["python", "-m", "pytest", "--ignore=tests"],
    ["python", "-m", "pytest", "--ignore-glob=test_*.py"],
    ["python", "-m", "pytest", "--override-ini=python_files=never.py"],
    ["python", "-m", "pytest", "--noconftest"],
])
def test_pytest_cannot_skip_the_judge(repo, command) -> None:
    with pytest.raises(CommandError, match="skip or replace the judge"):
        run_command(repo, command, timeout=10)


def test_pytest_binary_dash_c_is_a_replacement_config(repo) -> None:
    with pytest.raises(CommandError, match="replaces the judge config"):
        run_command(repo, ["pytest", "-c", "skip.ini", "-q"], timeout=10)


def test_an_ordinary_pytest_run_is_still_allowed(repo) -> None:
    """The loop's job is to run the judge, not to be unable to."""
    result = run_command(repo, ["python", "-m", "pytest", "-q"], timeout=30)
    assert result.exit_code != 0   # the fixture test is red on purpose
    assert result.ok is False
