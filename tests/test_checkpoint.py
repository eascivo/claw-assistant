"""World Checkpoint 单元测试。"""

import json
import tempfile
from pathlib import Path

import pytest
from claw_assistant.governance.checkpoint import (
    clear_postmortems,
    deviation,
    get_postmortems,
    run_checkpoint,
)


def test_deviation() -> None:
    assert deviation(100, 50) == -0.5
    assert deviation(100, 150) == 0.5
    assert deviation(0, 10) == 0.0


@pytest.mark.asyncio
async def test_run_checkpoint_no_validator_no_trigger() -> None:
    config = {
        "limbs": {"content": {}},
        "checkpoint": {"threshold": 0.5},
    }
    out = await run_checkpoint("content", {}, {"ok": True}, "t1", config)
    assert out["triggered"] is False
    assert out["deviation"] == 0.0


@pytest.mark.asyncio
async def test_run_checkpoint_content_stub_no_expected_skip() -> None:
    config = {
        "limbs": {"content": {"checkpoint": "content_stub"}},
        "checkpoint": {"threshold": 0.5},
    }
    out = await run_checkpoint("content", {}, {"ok": True}, "t1", config)
    assert out["triggered"] is False
    assert out["deviation"] == 0.0


@pytest.mark.asyncio
async def test_run_checkpoint_content_stub_deviation_under_threshold() -> None:
    clear_postmortems()
    config = {
        "limbs": {"content": {"checkpoint": "content_stub"}},
        "checkpoint": {"threshold": 0.5},
    }
    params = {"expectedWorldState": 100}
    result = {"ok": True, "mock_actual": 110}
    out = await run_checkpoint("content", params, result, "t1", config)
    assert out["deviation"] == pytest.approx(0.1)
    assert out["triggered"] is False
    assert len(get_postmortems()) == 0


@pytest.mark.asyncio
async def test_run_checkpoint_content_stub_deviation_over_threshold() -> None:
    clear_postmortems()
    config = {
        "limbs": {"content": {"checkpoint": "content_stub"}},
        "checkpoint": {"threshold": 0.5},
    }
    params = {"expectedWorldState": 100}
    result = {"ok": True, "mock_actual": 40}
    out = await run_checkpoint("content", params, result, "t1", config)
    assert out["deviation"] == pytest.approx(-0.6)
    assert out["triggered"] is True
    post = get_postmortems()
    assert len(post) == 1
    assert post[0]["task_id"] == "t1"
    assert post[0]["expected"] == 100
    assert post[0]["actual"] == 40
    assert post[0]["deviation"] == pytest.approx(-0.6)


@pytest.mark.asyncio
async def test_run_checkpoint_postmortem_file_sink() -> None:
    """复盘触发时若 checkpoint.postmortem_sink=file，则追加写入 JSONL 文件。"""
    clear_postmortems()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    try:
        config = {
            "limbs": {"content": {"checkpoint": "content_stub"}},
            "checkpoint": {"threshold": 0.5, "postmortem_sink": "file", "postmortem_file_path": str(path)},
        }
        params = {"expectedWorldState": 100}
        result = {"ok": True, "mock_actual": 40}
        out = await run_checkpoint("content", params, result, "t-file", config)
        assert out["triggered"] is True
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["task_id"] == "t-file"
        assert entry["expected"] == 100
        assert entry["actual"] == 40
    finally:
        path.unlink(missing_ok=True)
