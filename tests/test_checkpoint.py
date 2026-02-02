"""World Checkpoint 单元测试。"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from claw_assistant.governance.checkpoint import (
    clear_postmortems,
    deviation,
    get_postmortems,
    load_postmortems_from_file_into_memory,
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
async def test_run_checkpoint_postmortem_alert_event() -> None:
    """复盘触发且 total >= alert_after_postmortem_count 时，写入 postmortem_alert 事件。"""
    from claw_assistant.governance.events import clear_events, get_events

    clear_postmortems()
    clear_events()
    config = {
        "limbs": {"content": {"checkpoint": "content_stub"}},
        "checkpoint": {"threshold": 0.5, "alert_after_postmortem_count": 1},
    }
    params = {"expectedWorldState": 100}
    result = {"ok": True, "mock_actual": 40}
    await run_checkpoint("content", params, result, "t-alert", config)
    events = get_events()
    alert_events = [e for e in events if e.get("type") == "postmortem_alert"]
    assert len(alert_events) >= 1
    assert alert_events[0]["payload"]["total"] >= 1
    assert alert_events[0]["payload"]["threshold"] == 1


@pytest.mark.asyncio
async def test_run_checkpoint_alert_webhook_called() -> None:
    """复盘告警触发且配置 alert_webhook_url 时，POST 到该 URL。"""
    clear_postmortems()
    config = {
        "limbs": {"content": {"checkpoint": "content_stub"}},
        "checkpoint": {
            "threshold": 0.5,
            "alert_after_postmortem_count": 1,
            "alert_webhook_url": "http://test.example/alert",
        },
    }
    params = {"expectedWorldState": 100}
    result = {"ok": True, "mock_actual": 40}
    with patch("claw_assistant.governance.checkpoint.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        await run_checkpoint("content", params, result, "t-webhook", config)
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://test.example/alert"
    assert call_args[1]["json"] == {"event": "postmortem_alert", "total": 1, "threshold": 1}


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


def test_get_postmortems_merges_file_sink() -> None:
    """get_postmortems(config) 在 postmortem_sink=file 时合并 JSONL 文件中的复盘，按 task_id 去重。"""
    clear_postmortems()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
        f.write(json.dumps({"task_id": "from-file", "tool_name": "content", "expected": 1, "actual": 2, "deviation": 1.0, "params": {}, "result": {}}, ensure_ascii=False) + "\n")
    try:
        config = {"checkpoint": {"postmortem_sink": "file", "postmortem_file_path": str(path)}}
        post = get_postmortems(config)
        assert len(post) == 1
        assert post[0]["task_id"] == "from-file"
        # 内存有一条、文件有一条（不同 task_id）时返回两条
        from claw_assistant.governance.checkpoint import _postmortems
        _postmortems.append({"task_id": "from-memory", "tool_name": "content", "expected": 10, "actual": 5, "deviation": -0.5, "params": {}, "result": {}})
        post2 = get_postmortems(config)
        assert len(post2) == 2
        task_ids = {p["task_id"] for p in post2}
        assert task_ids == {"from-file", "from-memory"}
        # 同一 task_id 只保留一条（内存优先）
        _postmortems.clear()
        _postmortems.append({"task_id": "from-file", "tool_name": "content", "expected": 99, "actual": 98, "deviation": -0.01, "params": {}, "result": {}})
        post3 = get_postmortems(config)
        assert len(post3) == 1
        assert post3[0]["expected"] == 99  # 内存优先
    finally:
        path.unlink(missing_ok=True)
        clear_postmortems()


def test_load_postmortems_from_file_into_memory() -> None:
    """启动时从 JSONL 加载到内存：load_postmortems_from_file_into_memory 将文件条目 extend 到 _postmortems。"""
    clear_postmortems()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
        f.write(
            json.dumps(
                {"task_id": "startup-1", "tool_name": "content", "expected": 1, "actual": 2, "deviation": 1.0, "params": {}, "result": {}},
                ensure_ascii=False,
            )
            + "\n"
        )
    try:
        config = {"checkpoint": {"postmortem_sink": "file", "postmortem_file_path": str(path)}}
        n = load_postmortems_from_file_into_memory(config)
        assert n == 1
        from claw_assistant.governance.checkpoint import _postmortems
        assert len(_postmortems) == 1
        assert _postmortems[0]["task_id"] == "startup-1"
        assert get_postmortems(config)[0]["task_id"] == "startup-1"
    finally:
        path.unlink(missing_ok=True)
        clear_postmortems()
