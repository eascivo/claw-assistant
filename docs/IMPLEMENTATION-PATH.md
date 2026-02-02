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

完成上述即视为 Phase 1 闭环完成。

---

## 已迭代：Constitution + World Checkpoint

| 内容 | 说明 |
|------|------|
| **Constitution** | 配置 `constitution.forbid` / `restrict`；`hooks.constitution_violation` 检查；forbid 一律禁止，restrict 项必须配置 `require_approval`。 |
| **World Checkpoint** | 配置 `checkpoint.threshold`、`delay_seconds`；limb 可配置 `checkpoint: "content_stub"`；校验器注册 `register_validator`；偏差超阈值写复盘 `get_postmortems()`；API `GET /postmortems`。 |

- **校验器**：`governance/checkpoint.py` 中 `content_stub` 从 `params.expectedWorldState` 与 `result.mock_actual` 取期望/实际值；生产可替换为真实 API（如粉丝数）。
- **复盘**：内存列表，可扩展为 DB/向量库；Phase 1 提供 `GET /postmortems` 供 Dashboard 或人工查看。

---

## 下一步规划（Phase 2 / Phase 3）

**每完成一个阶段或重大功能后，在此更新「下一步规划」小节，便于持续对齐 [SYSTEM-DESIGN.md](SYSTEM-DESIGN.md) 与协作。**

### Phase 2 建议优先

| 内容 | 说明 |
|------|------|
| **Dashboard 时间轴** | 事件存储（审批 requested/resolved、limb 执行、postmortem）→ FastAPI 读事件 API → **Next.js + Tailwind** 前端：待审批、任务列表、24h 决策回放时间轴、postmortems。先有态势看板再接 Brain-B 更清晰。 |
| **Brain-B 影子测试** | 双 agent（main / experimental）；实验渠道任务先走 Brain-B，通过后再进 Brain-A 生产；依赖双 agent bindings 与任务路由。 |
| **Constitution 可选增强** | 可选 LLM 意图偏差分（deviationScore > threshold 则拦截）。 |

**依赖**：事件存储（内存 / Redis / SQLite 记录 approval、执行、postmortem）；Dashboard 后端读事件并暴露 API；前端连后端展示时间轴。

---

## 已迭代：Phase 2 Dashboard 时间轴

| 内容 | 说明 |
|------|------|
| **事件存储** | `governance/events.py`：`append_event(type, payload)`、`get_events(since_ts, limit)`；审批 register/resolve、limb 执行、postmortem 时写入。 |
| **读事件 API** | `GET /events?since_ts=&limit=`；Daemon 启用 CORS（localhost:3000）供前端调用。 |
| **Dashboard 前端** | `dashboard/`：Next.js 14 App Router + Tailwind；单页展示待审批、时间轴（最近 100 条）、复盘；`NEXT_PUBLIC_API_URL` 默认 `http://localhost:8080`；每 5s 刷新。 |

- **验收**：终端 1 `claw-assistant serve`，终端 2 `cd dashboard && npm run dev`，浏览器打开 http://localhost:3000，可见待审批 / 时间轴 / 复盘；跑一次 run → approve 后时间轴有事件。

---

## 已迭代：Brain-B 影子测试（channel 区分）

| 内容 | 说明 |
|------|------|
| **channel 参数** | `run_task_flow(..., channel="main"|"experimental")`；POST /run 支持 `channel`，CLI `run --channel experimental`。 |
| **事件与结果** | limb_executed 事件 payload 含 `channel`；返回 result 含 `channel`，便于 Dashboard/时间轴区分生产与影子。 |
| **审批** | main 与 experimental 共用同一审批流（require_approval 由 config 决定）；后续可配置 experimental 免审批仅记录。 |

- **验收**：`claw-assistant run --channel experimental "影子测试"`（或 approve 后）返回 `channel: experimental`；GET /events 中 limb_executed 含 `channel`。

---

## 已迭代：experimental 免审批

| 内容 | 说明 |
|------|------|
| **channels 配置** | `config.channels.experimental.require_approval` 默认 `false`；`get_channel_config(config, channel)` 读取。 |
| **task_flow** | 当 channel=experimental 且 `channels.experimental.require_approval=false` 时跳过审批，仅执行并记录事件。 |
| **main** | main channel 仍按 limb `require_approval`；可配置 `channels.experimental.require_approval: true` 使 experimental 也需审批。 |

- **验收**：`claw-assistant run --channel experimental "影子"` 在默认 config 下不挂起，直接返回成功；单测 `test_run_task_flow_experimental_skip_approval`、集成 `test_run_experimental_no_approval_when_skip`。

---

## 下一步规划（Phase 2 剩余 / Phase 3）

**每完成一个阶段或重大功能后，在此更新「下一步规划」小节。**

---

## 已迭代：Constitution 意图偏差分（可选）

| 内容 | 说明 |
|------|------|
| **intent_deviation 配置** | `constitution.intent_deviation.enabled`、`threshold`、`stub_score`（测试用）；未设 stub_score 时后续可接 LLM。 |
| **hooks** | `_intent_deviation_score` 返回 stub_score 或 None；`constitution_violation` 中 score > threshold 则拦截。 |
| **验收** | `intent_deviation.enabled=true` 且 `stub_score=1.0`、`threshold=0.5` 时 run 返回 block_reason constitution；单测 test_constitution_intent_deviation_*、test_run_task_flow_intent_deviation_block。 |

---

## 已迭代：多 Limb + 集成测试鲁棒性

| 内容 | 说明 |
|------|------|
| **多 Limb** | ops stub（`limbs/ops.py`）、`run`/API 支持可选 `tool`（content \| ops）、task_flow 按 `tool_name` 路由；`config.example.yaml` 含 limbs.content 与 limbs.ops。 |
| **集成测试鲁棒性** | `tests/conftest.py` 定义 `TEST_CONFIG`（content 需审批、experimental 免审批、intent_deviation 关闭）；`create_app(config=None)` 支持注入配置，集成测试通过 `app` fixture 使用 `create_app(config=TEST_CONFIG)`，与项目根 `config.yaml` 隔离。 |
| **验收** | `pytest tests/` 全部通过；任意本地 config（含智谱等）不影响集成测试结果。 |

---

## 下一步规划（Phase 2 收尾 / Phase 3）

**每完成一个阶段或重大功能后，在此更新「下一步规划」小节。**

### 已迭代：intent_deviation 接智谱 AI

| 内容 | 说明 |
|------|------|
| **当前支持** | `provider: zhipu` 时调用智谱 Chat Completions 算意图偏差分；需环境变量 `ZHIPUAI_API_KEY`；`base_url` / `model` 可配置。 |
| **扩展选项** | 接其他 LLM（如 OpenAI）时：在 `governance/intent_deviation.py` 新增 `intent_deviation_score_xxx(tool_name, params, config)`，在 `governance/hooks.py` 的 `_intent_deviation_score` 中按 `provider` 分支调用；配置中增加 `provider: openai` 及对应 base_url/model/env 说明即可。 |

### 已迭代：intent → tool 映射

| 内容 | 说明 |
|------|------|
| **config.intent_tool_map** | 可选列表，每项 `{ pattern: "正则", tool: "content"|"ops" }`，按顺序匹配 intent，先匹配先返回；未配置或无匹配时默认 content。 |
| **resolve_tool_from_intent** | `config.py` 中实现；task_flow / API 在未传 tool（或 tool 为空）时调用，得到 limb。 |
| **API / CLI** | `tool` 可选；省略时由服务端按 intent_tool_map 推断；显式传 tool 则覆盖。 |
| **验收** | 单测 test_config.resolve_tool_from_intent_*、test_task_flow_tool_inferred_from_intent；集成 test_run_tool_inferred_from_intent。 |

### 已迭代：复盘持久化（自动复盘小步）

| 内容 | 说明 |
|------|------|
| **checkpoint.postmortem_sink** | `memory`（默认，仅内存）或 `file`；`file` 时复盘同时追加到 JSONL 文件。 |
| **checkpoint.postmortem_file_path** | sink=file 时写入路径，默认 `postmortems.jsonl`；便于后续扩展为 DB/长期记忆。 |
| **验收** | 单测 test_run_checkpoint_postmortem_file_sink；GET /postmortems 仍读内存，文件为持久化备份。 |

### 已迭代：GET /postmortems 合并 JSONL（自动复盘扩展）

| 内容 | 说明 |
|------|------|
| **get_postmortems(config)** | config 可选；当 checkpoint.postmortem_sink=file 时从 JSONL 读取并与内存合并，按 task_id 去重（内存优先）。 |
| **GET /postmortems** | 使用 run_config 调用 get_postmortems(config)，返回内存 + 文件中的复盘。 |
| **验收** | 单测 test_get_postmortems_merges_file_sink；重启后或跨进程可通过文件看到历史复盘。 |

### 已迭代：启动时从 JSONL 加载复盘到内存

| 内容 | 说明 |
|------|------|
| **load_postmortems_from_file_into_memory(config)** | 将 JSONL 文件中的复盘 extend 到 _postmortems，返回本次加载条数；sink=file 时生效。 |
| **lifespan 启动** | FastAPI lifespan 内若 config.checkpoint.postmortem_sink=file，调用 load_postmortems_from_file_into_memory，重启后 GET /postmortems 即含历史复盘。 |
| **验收** | 单测 test_load_postmortems_from_file_into_memory。 |

### 已迭代：多 Limb 增强（notify stub）

| 内容 | 说明 |
|------|------|
| **notify limb** | `limbs/notify.py` stub；LIMB_REGISTRY 注册 content / ops / notify。 |
| **config.example** | limbs.notify + intent_tool_map 示例「通知\|提醒」→ notify。 |
| **TEST_CONFIG** | conftest 含 limbs.notify；单测/集成测 tool=notify、intent 推断 notify。 |
| **验收** | test_run_task_flow_tool_notify、test_run_tool_notify、test_run_tool_inferred_from_intent 含 notify。 |

### 已迭代：GET /postmortems 收益指标小步（summary）

| 内容 | 说明 |
|------|------|
| **GET /postmortems** | 响应增加 `summary: { total: N }`，N 为复盘条数；供 Dashboard/告警做收益指标用。 |
| **验收** | 集成测 test_get_postmortems_returns_summary；Dashboard 仍用 postmortems 列表，兼容。 |

### 已迭代：复盘告警（total 超阈值）

| 内容 | 说明 |
|------|------|
| **checkpoint.alert_after_postmortem_count** | 可选；复盘条数 >= 此值时 GET /postmortems 的 summary.alert 为 true，summary.alert_threshold 为配置值。 |
| **验收** | 集成测 test_get_postmortems_summary_alert_when_over_threshold；config.example 注释示例。 |

### 已迭代：告警事件写入 events

| 内容 | 说明 |
|------|------|
| **_write_postmortem** | 当 config.checkpoint.alert_after_postmortem_count 存在且 total >= 阈值时，append_event("postmortem_alert", { total, threshold })，供时间轴/告警消费。 |
| **验收** | 单测 test_run_checkpoint_postmortem_alert_event；GET /events 可见 postmortem_alert 类型。 |

### 已迭代：last_24h 指标

| 内容 | 说明 |
|------|------|
| **复盘 entry.created_at** | _write_postmortem 写入时增加 created_at（time.time()），便于按时间过滤。 |
| **GET /postmortems summary.last_24h** | 过去 24 小时内 created_at 的复盘条数；无 created_at 的条目（如旧文件）不计入。 |
| **验收** | 集成测 test_get_postmortems_returns_summary 断言 summary.last_24h 存在且 last_24h <= total。 |

### 已迭代：可观测小步（GET /health）

| 内容 | 说明 |
|------|------|
| **GET /health** | 健康检查，返回 `{ "status": "ok" }`，供负载均衡/监控探测。 |
| **验收** | 集成测 test_get_health。 |

### 已迭代：GET /metrics 基础指标

| 内容 | 说明 |
|------|------|
| **GET /metrics** | 返回 `postmortem_total`、`postmortem_last_24h`、`pending_count`、`events_count`、`run_count`，供监控/可观测。 |
| **get_events_count() / get_run_count()** | `governance/events.py` 中实现；run_count 为 limb_executed 事件数。 |
| **验收** | 集成测 test_get_metrics 断言 events_count、run_count 存在且为 int。 |

### Phase 3 再往后

- **多 Limb 增强**：更多 limbs 注册、intent_tool_map 扩展。
- **商业闭环稳定**：可回放、可收敛；可观测可按需继续扩展。
