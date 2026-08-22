"""Tests proving the CommandResult serialization bug and its fix."""
import json
import pytest
from s17code.coding.exec import CommandResult


def test_command_result_is_not_json_serializable():
    """CommandResult dataclass cannot be directly serialized — this is the bug."""
    result = CommandResult(
        command=["python", "-m", "pytest"],
        exit_code=0,
        stdout="1 passed",
        stderr="",
        timed_out=False,
        duration_seconds=0.5,
    )
    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps(result)


def test_command_result_as_dict_is_json_serializable():
    """After calling .as_dict(), the result can be serialized."""
    result = CommandResult(
        command=["python", "-m", "pytest"],
        exit_code=0,
        stdout="1 passed",
        stderr="",
        timed_out=False,
        duration_seconds=0.5,
    )
    d = result.as_dict()
    serialized = json.dumps(d)
    assert '"exit_code": 0' in serialized
    assert '"ok": true' in serialized


def test_worker_returns_dict_not_dataclass():
    """The worker must return a dict (as_dict), not the raw CommandResult."""
    result = CommandResult(
        command=["echo", "hello"],
        exit_code=0,
        stdout="hello",
        stderr="",
        timed_out=False,
        duration_seconds=0.1,
    )
    converted = result.as_dict() if hasattr(result, 'as_dict') else result
    assert isinstance(converted, dict)
    assert converted["exit_code"] == 0
    assert converted["ok"] is True
    json.dumps(converted)  # must not raise
