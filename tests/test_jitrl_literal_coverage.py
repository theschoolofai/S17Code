"""A rewrite may not drop the anchor, whatever language the anchor is in.

`jitrl` declines its own rewrite when a literal the user supplied disappears —
"a path, a version, a sha, an issue number, anything in quotes". Paths were
recognised by an extension allowlist covering Python and the web, so a path in
any other language was not seen as a path and could be dropped silently. URLs
were only caught when they happened to end in a listed extension.

Dropping the path is the exact failure the module exists to prevent: the planner
then spends its first nodes rediscovering where to look.
"""
from __future__ import annotations

import pytest

from s17code.reasoning.jitrl import literals


@pytest.mark.parametrize("text,expected", [
    ("fix the panic in src/auth/server.rs", "src/auth/server.rs"),
    ("the bug is in handler.go", "handler.go"),
    ("patch Main.java", "Main.java"),
    ("update setup.cfg", "setup.cfg"),
    ("fix deploy.sh", "deploy.sh"),
    ("the header in include/parser.h", "include/parser.h"),
    ("fix lib.rb", "lib.rb"),
    ("check Cargo.lock", "Cargo.lock"),
    (r"open src\pkg\main.c", r"src\pkg\main.c"),
])
def test_paths_outside_the_python_and_web_extensions_are_literals(text, expected):
    assert expected in literals(text)


@pytest.mark.parametrize("text,expected", [
    ("see https://example.com/rfc/page for the spec", "https://example.com/rfc/page"),
    ("read http://localhost:8113/v1/catalog", "http://localhost:8113/v1/catalog"),
])
def test_urls_are_literals_even_without_a_file_extension(text, expected):
    assert expected in literals(text)


def test_the_directory_a_request_names_is_a_literal():
    assert "src/auth/" in literals("the problem is somewhere in src/auth/")


@pytest.mark.parametrize("prose", [
    "make it faster, e.g. by caching",
    "the login is broken and/or slow",
    "i.e. the request should be idempotent",
    "explain this clearly and concisely",
])
def test_ordinary_prose_yields_no_literals(prose):
    """Over-matching is not free: every false literal is a refused rewrite."""
    assert literals(prose) == set(), f"false literals in {prose!r}: {literals(prose)}"


def test_what_already_worked_still_works():
    assert "tests/test_login.py" in literals("fix the failing test in tests/test_login.py")
    assert "3.11" in literals("this needs python 3.11")
    assert "#412" in literals("see issue #412")
    assert "deadbeef1234" in literals("the regression landed in deadbeef1234")
    assert "keep this exact phrase" in literals('say "keep this exact phrase"')
