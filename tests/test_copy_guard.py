"""copy_code_file must respect the protected-path guard like every other write."""
from __future__ import annotations

import pytest

from s17code.coding.edit import EditLedger, copy_within_workspace, create_file
from s17code.coding.guard import GuardError
from s17code.coding.workspace import Workspace


@pytest.fixture()
def workspace(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "tests").mkdir()
    (root / "tests" / "test_judge.py").write_text("def test_real():\n    assert 1 + 1 == 2\n")
    (root / ".git").mkdir()
    return Workspace.open(root)


def test_copy_over_protected_test_is_refused(workspace):
    ledger = EditLedger()
    create_file(workspace, ledger, "payload.txt", content="def test_fake():\n    assert True\n")
    with pytest.raises(GuardError):
        copy_within_workspace(workspace, ledger, "payload.txt", "tests/test_judge.py",
                              overwrite=True)
    assert "assert 1 + 1 == 2" in (workspace.root / "tests" / "test_judge.py").read_text()


def test_copy_into_protected_tree_is_refused(workspace):
    ledger = EditLedger()
    create_file(workspace, ledger, "payload.txt", content="x = 1\n")
    with pytest.raises(GuardError):
        copy_within_workspace(workspace, ledger, "payload.txt", "tests/test_new.py")
    assert not (workspace.root / "tests" / "test_new.py").exists()


def test_copy_to_unprotected_path_still_works(workspace):
    ledger = EditLedger()
    create_file(workspace, ledger, "a.txt", content="hello\n")
    result = copy_within_workspace(workspace, ledger, "a.txt", "b.txt")
    assert result["copied"] is True
    assert (workspace.root / "b.txt").read_text() == "hello\n"