# claw-assistant MVP 实现路径

**与 [SYSTEM-DESIGN.md](SYSTEM-DESIGN.md) Phase 1 对齐的拆分与目录结构。**

---

## 技术栈（与规则一致）

- **后端 / Daemon / CLI**：Python（FastAPI + CLI）
- **前端 / Dashboard**：Phase 2 再上，TypeScript（Next.js + Tailwind）

---

## Phase 1 范围（约 2 周）

| 内容 | 说明 |
|------|------|
| 单 Brain-A | 暂用「意图 → 单任务」的简单映射，不接 OpenClaw |
| 单 Limb（Content） | Stub：接收任务仅打 log，返回占位结果 |
| Proxy + 人工审批 | ApprovalManager 内存实现；需审批的 task 挂起，等 approve/reject |
| World Checkpoint | 占位：after_tool_call 打 log，不拉真实 API |

**依赖**：无 OpenClaw；本地 HTTP daemon + CLI 即可跑通「run → 挂起 → approve → limb 执行」闭环。

---

## 目录结构（Phase 1）

```text
claw-assistant/
├── pyproject.toml          # 项目与依赖
├── requirements.txt        # 可选的 pip 依赖列表
├── src/
│   └── claw_assistant/
│       ├── __init__.py
│       ├── main.py         # CLI 入口（serve / run / status / approve / reject）
│       ├── config.py       # 配置加载（YAML，limbs、require_approval 等）
│       ├── governance/
│       │   ├── __init__.py
│       │   ├── approval.py # ApprovalManager（内存）
│       │   ├── task_flow.py# runTaskFlow：Constitution / 审批 / 幂等 / 派发 Limb
│       │   └── hooks.py    # before_tool_call / after_tool_call 逻辑
│       ├── limbs/
│       │   ├── __init__.py
│       │   ├── base.py     # Limb 接口
│       │   └── content.py  # Content Limb（stub）
│       └── server/
│           ├── __init__.py
│           └── app.py      # FastAPI：POST /run, GET /status, POST /approve, POST /reject
├── tests/
│   ├── __init__.py
│   ├── test_approval.py
│   ├── test_task_flow.py
│   └── test_integration.py # 端到端：run → status → approve → 结果
├── config.example.yaml
└── docs/
    └── ...
```

---

## 实现顺序

1. **配置与 ApprovalManager**：`config.py` 读 YAML；`approval.py` 内存存挂起任务，`register`/`wait`/`resolve`。
2. **Task 流**：`task_flow.py` 实现 `run_task_flow(intent)`：生成 task → Constitution 检查（占位通过）→ 若需审批则挂起 → 幂等检查（占位通过）→ 调用 Limb。
3. **Limb Content stub**：`limbs/content.py` 接收 task，打 log，返回固定结构。
4. **Daemon**：FastAPI 暴露 `/run`、`/status`、`/approve`、`/reject`，内部调 governance + limbs。
5. **CLI**：`main.py` 用 `typer` 或 `argparse` 实现 `serve`（起 uvicorn）、`run`（POST /run）、`status`（GET /status）、`approve`/`reject`（POST）。
6. **测试**：先单测 approval、task_flow，再集成测「run → status → approve → 校验结果」。

---

## 验收标准（Phase 1）

- 终端 1：`claw-assistant serve` 或 `uvicorn` 启动，监听 8080。
- 终端 2：`claw-assistant run "发布一条测试"` → 任务挂起，返回或提示「待审批 approval_id」。
- 终端 3：`claw-assistant status` 列出待审批；`claw-assistant approve <id>` 解挂。
- 终端 2：收到执行结果；Content Limb 的 log 可见（stub 输出）。
- `pytest tests/` 全部通过。

完成上述即视为 Phase 1 闭环完成，可再迭代 Constitution、World Checkpoint 真实校验与 OpenClaw 对接。
