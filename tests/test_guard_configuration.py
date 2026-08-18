"""Configuration must not be able to quietly weaken the guard.

The agent may not edit the thing that grades it. `S17_PROTECTED_PATHS` overrides
`DEFAULT_PROTECTED` wholesale rather than extending it, so any shipped example
value is a live setting, not documentation: whatever it omits becomes editable
the moment someone follows the README's `cp .env.example .env`.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from s17code.coding.guard import DEFAULT_PROTECTED, is_protected, protected_patterns

ROOT = Path(__file__).resolve().parents[1]

# Layouts a real repository uses. Every one of these grades the agent's work.
JUDGE_PATHS = (
    "tests/test_calc.py",
    "test/test_x.py",
    "src/tests/test_deep.py",
    "src/pkg/test_thing.py",
    "src/pkg/thing_test.py",
    "conftest.py",
    "src/conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    ".github/workflows/ci.yml",
)


def test_every_judge_path_is_protected_by_default() -> None:
    unguarded = [p for p in JUDGE_PATHS if not is_protected(p, DEFAULT_PROTECTED)]
    assert unguarded == [], f"DEFAULT_PROTECTED leaves these editable: {unguarded}"


def test_the_shipped_example_env_does_not_narrow_the_guard() -> None:
    """`cp .env.example .env` is the README's own setup step.

    Leaving the key out of the example is fine — the built-in default then
    applies. Shipping a shorter list is not: it silently unprotects everything
    the shorter list forgot, on every checkout that follows the instructions.
    """
    configured = dotenv_values(ROOT / ".env.example").get("S17_PROTECTED_PATHS")
    if not configured:
        return  # unset in the example, so DEFAULT_PROTECTED applies

    patterns = tuple(p.strip() for p in configured.split(",") if p.strip())
    lost = [p for p in JUDGE_PATHS if is_protected(p, DEFAULT_PROTECTED) and not is_protected(p, patterns)]
    assert lost == [], (
        f"S17_PROTECTED_PATHS in .env.example unprotects {len(lost)} of "
        f"{len(JUDGE_PATHS)} judge paths that DEFAULT_PROTECTED covers: {lost}"
    )


def test_the_suite_does_not_inherit_a_developers_protected_paths() -> None:
    """A local .env must not decide what this suite proves.

    Without the session fixture in conftest, `s17code.main`'s import-time
    `load_dotenv()` puts the developer's `S17_PROTECTED_PATHS` into the
    environment and every later guard assertion silently tests that instead.
    """
    assert protected_patterns() == DEFAULT_PROTECTED
