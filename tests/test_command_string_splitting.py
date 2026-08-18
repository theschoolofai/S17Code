"""A command given as a string must survive being split.

`run_command` accepts `str | list[str]` and splits a string with
`shlex.split`, which defaults to POSIX mode. In POSIX mode the backslash is an
escape character, so every Windows path handed in as a string was silently
rewritten into a different path — not refused, rewritten. The agent then reads
"no such file" about a path it never asked for.
"""
from __future__ import annotations

import pathlib

import pytest

from s17code.coding.exec import split_command


@pytest.mark.parametrize("command,expected", [
    (r"python C:\Users\me\proj\stability_test.py",
     ["python", r"C:\Users\me\proj\stability_test.py"]),
    (r"pytest tests\test_calc.py -q",
     ["pytest", r"tests\test_calc.py", "-q"]),
    (r"python src\pkg\main.py --flag",
     ["python", r"src\pkg\main.py", "--flag"]),
])
def test_backslash_paths_survive(command, expected):
    assert split_command(command) == expected


@pytest.mark.parametrize("command,expected", [
    ("python -m pytest -q", ["python", "-m", "pytest", "-q"]),
    ("pytest tests/test_calc.py", ["pytest", "tests/test_calc.py"]),
    ('pytest "tests/a b.py"', ["pytest", "tests/a b.py"]),
    ("pytest 'tests/a b.py'", ["pytest", "tests/a b.py"]),
    ("  pytest   -q  ", ["pytest", "-q"]),
])
def test_the_ordinary_forms_are_unchanged(command, expected):
    assert split_command(command) == expected


def test_a_list_is_passed_through_untouched():
    argv = ["python", r"C:\a\b.py"]
    assert split_command(argv) == argv
    assert split_command(argv) is not argv, "must not alias the caller's list"


def test_the_split_path_is_the_path_that_runs(tmp_path):
    """End to end: a backslash path in a string command actually executes.

    This is the failure the unit cases above describe, at the boundary that
    matters — the file exists, and before the fix the interpreter was handed a
    mangled name and could not find it.
    """
    from s17code.coding.exec import run_command
    from s17code.coding.workspace import Workspace

    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    (nested / "probe.py").write_text("print('found me')\n", encoding="utf-8")

    result = run_command(Workspace(pathlib.Path(tmp_path)),
                         r"python src\pkg\probe.py", timeout=60)
    assert "found me" in result.stdout, f"exit={result.exit_code} stderr={result.stderr[:200]}"
