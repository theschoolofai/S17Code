"""The output of read_code must be usable as the anchor for edit_code.

`apply_edit` requires `old_string` to match the file byte for byte, and
`ledger.require_read` means the agent *must* call `read_code` first. But
`read_code` returns the file with a line-number gutter — `f"{n:>6}  {line}"` —
which is the only representation of the file the agent ever sees. Copy an anchor
out of it and the edit can never match.

Observed on a real run, six times in a row on the same node:

    fix_average_py    failed  EditError: old_string does not appear in average.py.
    fix_average_py_2  failed  EditError: old_string does not appear in average.py.
    ... x6, and the verification never re-ran, so the loop never went green.
"""
from __future__ import annotations

import re

import pytest

from s17code.coding.edit import EditError, EditLedger, apply_edit, read_code
from s17code.coding.workspace import Workspace


def assert_no_line_numbers_in(body: str) -> None:
    """No line of the file may begin with a line number.

    The first version of this check looked for the padded gutter ("     3"), so a
    real run that wrote "3      return ..." — the same gutter with its leading
    spaces trimmed — passed the test while corrupting the file. Assert the
    property, not one spelling of its violation.
    """
    for number, line in enumerate(body.splitlines(), 1):
        assert not re.match(r"^\s*\d+\s", line), (
            f"line {number} begins with a line number, so the gutter was written "
            f"into the file: {line!r}"
        )


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "average.py").write_text(
        'def average(numbers):\n'
        '    """Mean of a list. Returns 0 for an empty list."""\n'
        '    return sum(numbers) / len(numbers)\n',
        encoding="utf-8",
    )
    return Workspace(tmp_path)


def test_an_anchor_copied_from_read_code_output_works(repo):
    """The whole point: chain the two capabilities the way the runtime forces."""
    ledger = EditLedger()
    seen = read_code(repo, ledger, "average.py")

    # Exactly what a model has in front of it, gutter and all.
    anchor = "\n".join(seen["text"].splitlines()[2:3])
    assert anchor.lstrip().startswith("3"), "fixture assumes the numbered view"

    result = apply_edit(
        repo, ledger, "average.py",
        old_string=anchor,
        new_string="    return sum(numbers) / len(numbers) if numbers else 0",
    )
    assert result["replaced"] == 1
    body = (repo.root / "average.py").read_text(encoding="utf-8")
    assert "if numbers else 0" in body
    assert_no_line_numbers_in(body)


def test_a_numbered_replacement_is_refused_not_guessed_at(repo):
    """The anchor may carry the gutter. The replacement may not.

    An anchor is checked — strip it wrongly and it fails to match. A replacement
    is free text written straight into the file, so there is nothing to check it
    against. Both guesses were tried on real runs first. Writing it verbatim put
    a line number in the source:

        3      return sum(numbers) / len(numbers) if numbers else 0

    and de-guttering it line by line could not recover the indentation when the
    widths were uneven, producing Python that did not parse:

        if not numbers:
                return 0
            return sum(numbers) / len(numbers)
    """
    ledger = EditLedger()
    seen = read_code(repo, ledger, "average.py")
    before = (repo.root / "average.py").read_text(encoding="utf-8")

    with pytest.raises(EditError, match="line numbers"):
        apply_edit(repo, ledger, "average.py",
                   old_string=seen["text"].splitlines()[2],
                   new_string="3      return sum(numbers) / len(numbers) if numbers else 0")

    assert (repo.root / "average.py").read_text(encoding="utf-8") == before,         "a refused edit must not touch the file"


def test_read_code_offers_the_unnumbered_lines_too(repo):
    """So a caller never has to reconstruct the anchor from the numbered view."""
    ledger = EditLedger()
    seen = read_code(repo, ledger, "average.py")

    assert seen["content"].splitlines()[2] == "    return sum(numbers) / len(numbers)"
    assert_no_line_numbers_in(seen["content"])

    apply_edit(repo, ledger, "average.py",
               old_string=seen["content"].splitlines()[2],
               new_string=("    if not numbers:\n"
                           "        return 0\n"
                           "    return sum(numbers) / len(numbers)"))

    namespace: dict = {}
    exec((repo.root / "average.py").read_text(encoding="utf-8"), namespace)  # noqa: S102
    assert namespace["average"]([]) == 0
    assert namespace["average"]([1, 2, 3]) == 2


def test_a_multi_line_anchor_from_read_output_works(repo):
    ledger = EditLedger()
    seen = read_code(repo, ledger, "average.py")
    anchor = "\n".join(seen["text"].splitlines()[1:3])

    apply_edit(repo, ledger, "average.py", old_string=anchor,
               new_string='    """Mean, or 0."""\n    return sum(numbers) / len(numbers) if numbers else 0')
    body = (repo.root / "average.py").read_text(encoding="utf-8")
    assert "Mean, or 0." in body
    assert "if numbers else 0" in body


def test_a_plain_unnumbered_anchor_still_works(repo):
    ledger = EditLedger()
    read_code(repo, ledger, "average.py")
    apply_edit(repo, ledger, "average.py",
               old_string="    return sum(numbers) / len(numbers)",
               new_string="    return 0 if not numbers else sum(numbers) / len(numbers)")
    assert "0 if not numbers" in (repo.root / "average.py").read_text(encoding="utf-8")


def test_content_that_genuinely_looks_numbered_is_preferred_literally(tmp_path):
    """A file whose own text carries a numbered gutter must not be mangled.

    If the literal anchor matches, it wins. De-guttering is only ever a fallback
    for an anchor that matches nothing as given.
    """
    (tmp_path / "log.txt").write_text("     1  alpha\n     2  beta\n", encoding="utf-8")
    repo = Workspace(tmp_path)
    ledger = EditLedger()
    read_code(repo, ledger, "log.txt")

    apply_edit(repo, ledger, "log.txt", old_string="     2  beta", new_string="     2  BETA")
    assert (tmp_path / "log.txt").read_text(encoding="utf-8") == "     1  alpha\n     2  BETA\n"


def test_a_still_unmatchable_anchor_says_the_numbering_is_not_part_of_the_file(repo):
    ledger = EditLedger()
    read_code(repo, ledger, "average.py")
    with pytest.raises(EditError) as raised:
        apply_edit(repo, ledger, "average.py", old_string="nothing like this exists",
                   new_string="x")
    message = str(raised.value)
    assert "does not appear" in message
    assert "line number" in message.lower(), "the error should name the most likely cause"


def test_ambiguity_is_still_refused_after_de_guttering(tmp_path):
    (tmp_path / "d.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    repo = Workspace(tmp_path)
    ledger = EditLedger()
    seen = read_code(repo, ledger, "d.py")
    anchor = seen["text"].splitlines()[0]          # "     1  x = 1"

    with pytest.raises(EditError, match="appears 2 times"):
        apply_edit(repo, ledger, "d.py", old_string=anchor, new_string="x = 2")
