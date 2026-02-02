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

### 已迭代：GET /metrics 监控扩展（P3）

| 内容 | 说明 |
|------|------|
| **get_run_count_by_limb() / get_run_count_by_channel()** | `governance/events.py`：按 limb_executed 的 payload.tool_name、payload.channel 统计次数，返回 dict[str, int]。 |
| **GET /metrics** | 响应增加 `run_count_by_limb`、`run_count_by_channel`，供按 limb/channel 监控。 |
| **验收** | 单测 test_get_run_count_by_limb、test_get_run_count_by_channel 等；集成测 test_get_metrics 断言新字段存在且为 dict。 |

### 已迭代：告警渠道 Webhook（P4）

| 内容 | 说明 |
|------|------|
| **checkpoint.alert_webhook_url** | 可选；复盘条数 ≥ alert_after_postmortem_count 时，除写入 postmortem_alert 事件外，POST JSON（event/postmortem_alert, total, threshold）到该 URL；失败仅打 log。 |
| **_send_alert_webhook(url, payload)** | `governance/checkpoint.py`：httpx.post(url, json=payload, timeout=5.0)；4xx/5xx 或异常仅 logger.warning。 |
| **验收** | 单测 test_run_checkpoint_alert_webhook_called（patch httpx.post 断言调用）；集成测 test_app_with_alert_webhook_config；config.example 注释示例。 |

### 已迭代：IM 预留接口（发送审批通知 + Feishu stub）

| 内容 | 说明 |
|------|------|
| **IMNotifier 协议** | `im/notifier.py`：send_approval_request(approval_id, task_id, tool_name, summary, risk)；飞书/钉钉/Discord 按同一接口实现。 |
| **get_notifier(config)** | 根据 config.im.provider（feishu \| 空）返回 FeishuNotifier 或 NoOpNotifier；未配置则不推送。 |
| **FeishuNotifier** | stub：占位实现，可读 im.feishu.webhook_url；当前 send_approval_request 仅 log，后续接 Webhook 或发消息 API。 |
| **task_flow** | 审批 register 后调用 get_notifier(config).send_approval_request(**pending.to_public())，不阻塞。 |
| **验收** | 单测 test_im.get_notifier_*、send_approval_request 不崩溃；config.example 注释 im.provider、im.feishu.webhook_url。 |

### 已迭代：新增 Limb 文档说明

| 内容 | 说明 |
|------|------|
| **README「扩展：新增 Limb」** | 三步：实现 execute_xxx、在 LIMB_REGISTRY 注册、在 config limbs + intent_tool_map 配置；当前已注册 content / ops / notify。 |

### 已迭代：GET /events task_id 过滤（可回放小步）

| 内容 | 说明 |
|------|------|
| **get_events(task_id=...)** | `governance/events.py` 增加可选参数 task_id；过滤 payload.task_id 等于该值的事件，供单任务回放。 |
| **GET /events?task_id=xxx** | API 已支持 task_id 查询参数，委托 get_events(since_ts, limit, task_id) 返回过滤后列表。 |
| **验收** | 单测 test_get_events_task_id；集成测 test_get_events_filter_by_task_id。 |

### 已迭代：回放 UI（Dashboard 按 task_id 下钻）

| 内容 | 说明 |
|------|------|
| **时间轴筛选** | Dashboard 时间轴区块增加「按任务回放」下拉：选项为「全部」+ 当前事件中出现的 task_id（去重）；选「全部」时请求 GET /events?limit=100，选某 task_id 时请求 GET /events?task_id=xxx&limit=100。 |
| **taskIds 来源** | 仅在「全部」模式下从返回事件中提取 payload.task_id 去重并更新下拉列表；单任务模式下保持上一轮列表，便于切回「全部」后仍可再选其他任务。 |
| **验收** | 前端可选中某 task_id 后仅展示该任务事件；选「全部」恢复全局时间轴；npm run build 通过。 |

### 可收敛（最小形态）文档定义

| 内容 | 说明 |
|------|------|
| **输入** | 复盘条数（get_postmortems）、告警阈值（config.checkpoint.alert_after_postmortem_count）；后续可扩展偏差类型汇总、按 limb 统计等。 |
| **输出** | 建议列表，每项 `{ "id", "text", "source" }`；供 Dashboard 展示或人工决策；后续可扩展写回 config、自动调参。 |
| **流程** | 复盘/告警 → 汇总（如 total ≥ threshold）→ 生成建议文案 → 返回 API；人类根据建议改配置或确认，形成「可收敛」闭环。 |

### 已迭代：可收敛小步（文档定义 + 占位 API）

| 内容 | 说明 |
|------|------|
| **get_convergence_suggestions(postmortems, config)** | `governance/convergence.py`：根据复盘条数与 alert_after_postmortem_count 生成占位建议；total ≥ 阈值时返回一条「建议检查 checkpoint 阈值或复盘原因」。 |
| **GET /convergence/suggestions** | 占位 API：调用 get_postmortems(config) 与 get_convergence_suggestions(postmortems, config)，返回 `{ "suggestions": [...] }`。 |
| **验收** | 单测 test_convergence.get_convergence_suggestions_*；集成测 test_get_convergence_suggestions。 |

### 已迭代：Dashboard 展示可收敛建议

| 内容 | 说明 |
|------|------|
| **可收敛建议区块** | Dashboard 增加「可收敛建议」区块：与待审批/时间轴/复盘同一轮询，请求 GET /convergence/suggestions，展示 suggestions 列表（id、text、source）。 |
| **验收** | npm run build 通过；与复盘同频刷新，无建议时显示「暂无建议」。 |

### Phase 3 再往后

- **多 Limb 增强**：当前阶段已收尾（content / ops / notify 注册、intent_tool_map、扩展文档齐全）；后续按 [README 扩展：新增 Limb](README.md) 即可增加新 limb 与 intent_tool_map。
- **可回放小步**：GET /events 已支持 task_id 过滤，单任务回放 API 就绪；后续可做回放 UI 或按 task 聚合展示。
- **商业闭环稳定**：可收敛；可观测可按需继续扩展。

---

## 战略蓝图 vs 当前完成度对比

**对照文档**：[SYSTEM-DESIGN.md](SYSTEM-DESIGN.md)（HOTL 主权 AI 执行系统：多脑 + 治理审计 + 本地执行集群）

### 按 MVP 落地路径（不接 OpenClaw）的完成度

| 阶段 | 蓝图内容 | 当前状态 | 完成度 |
|------|----------|----------|--------|
| **Phase 1** | 单 Brain-A；单 Limb（Content）；Proxy + 人工审批；World Checkpoint（占位） | 全部完成；且 Constitution、Checkpoint 校验器与复盘已实现 | **100%** |
| **Phase 2** | Brain-B 影子测试；Constitution v1；Dashboard 时间轴 | channel main/experimental、experimental 免审批、Constitution forbid/restrict + 意图偏差（智谱）、事件存储 + GET /events、Dashboard 待审批+时间轴+复盘 | **100%** |
| **Phase 3** | 多 Limb；自动复盘；商业闭环稳定 | 多 Limb、复盘持久化+告警、health/metrics、回放 UI、可收敛小步、**GET /metrics 按 limb/channel 扩展**；告警渠道（Webhook）待后续 | **约 95%** |

**整体 MVP（不含 OpenClaw）完成度：约 98%。**

### 与全量战略蓝图的偏差

| 维度 | 蓝图目标 | 当前实现 | 偏差说明 |
|------|----------|----------|----------|
| **Control 双脑** | OpenClaw Brain-A/B 多 agent，意图/任务由 agent 模型+workspace 产出 | 意图→单任务简单映射，无 OpenClaw；channel 仅区分 main/experimental 路由与审批策略 | **刻意脱耦**：MVP 不依赖 OpenClaw，便于本地闭环验证 |
| **Commander** | IM Bot + Dashboard，经 OpenClaw Gateway WS/RPC（health、exec.approval、sessions） | 仅 Dashboard（Next.js）+ FastAPI HTTP API；无 IM Bot、无 Gateway WS | **未做**：IM Bot、Gateway 对接 |
| **Governance** | OpenClaw Plugin（before/after_tool_call、exec 审批） | 独立 FastAPI + 内存 ApprovalManager + hooks；逻辑与蓝图一致，未寄生 OpenClaw | **形态不同**：能力对齐，部署形态独立 |
| **Data / Limbs** | OpenClaw tools + Node/隧道，Limb 经 Gateway 调度 | 多 Limb 为进程内 stub，经 task_flow 直接调用；无 OpenClaw 工具注册与隧道 | **未做**：OpenClaw 工具注册与本地 Limb 隧道 |
| **可回放** | Dashboard 从 session transcript + 审批事件做时间轴 | 事件存储 + GET /events（含 task_id 过滤）；Dashboard 时间轴 + 按 task_id 下拉筛选单任务回放 | **已补齐**：回放 API 与回放 UI 均已就绪 |
| **可收敛** | 复盘回写、收益指标、告警后形成闭环 | 复盘持久化、summary、告警事件已做；**可收敛最小形态**：文档定义 + GET /convergence/suggestions 占位（复盘 ≥ 阈值时返回建议）；自动写回 config 未做 | **小步已做**：文档 + 占位 API；扩展为自动调参/写回 config 待后续 |

### 完成度小结

- **相对 MVP 路径（IMPLEMENTATION-PATH 约定）**：Phase 1/2 已收尾，Phase 3 收尾完成（回放 UI、可收敛小步、监控扩展），**整体约 98%**。剩余：可收敛扩展（写回 config/自动调参）等可选扩展；**告警渠道（Webhook）暂不列入近期**。
- **相对全量 SYSTEM-DESIGN**：核心治理与任务流、Dashboard 与可观测已对齐；**未覆盖**：OpenClaw 接入、IM Bot、Gateway WS/RPC、Limb 经 OpenClaw 调度与隧道。若按「全量蓝图」计，完成度约 **55%**（治理+数据流+Dashboard 为主，Control/Commander/Data 形态未接 OpenClaw）。

---

## 下一阶段 Roadmap（Phase 3 收尾 → Phase 4 选项）

### 近期（Phase 3 收尾，约 1–2 周）

| 优先级 | 项 | 说明 | 验收 |
|--------|----|------|------|
| ~~P1~~ | **回放 UI**（已完成） | Dashboard 支持按 task 查看：调用 GET /events?task_id=xxx，单任务时间轴下拉筛选 | 前端可选中某 task_id，仅展示该任务事件；见「已迭代：回放 UI」 |
| ~~P2~~ | **可收敛小步**（已完成） | 定义「收敛」最小形态（输入/输出/流程）；GET /convergence/suggestions 占位 API；复盘 ≥ 阈值时返回一条建议 | 文档定义 + 占位 API；见「已迭代：可收敛小步」 |
| ~~P3~~ | **监控扩展**（已完成） | GET /metrics 增加 run_count_by_limb、run_count_by_channel | 单测/集成测；见「已迭代：GET /metrics 监控扩展」 |
| ~~P4~~ | **告警渠道（Webhook）**（已完成） | checkpoint.alert_webhook_url；复盘 ≥ 阈值时 POST JSON（event/postmortem_alert, total, threshold） | 配置项 + 单测/集成测；见「已迭代：告警渠道 Webhook」 |

### 中期（Phase 4 方向选择，二选一或并行）

| 方向 | 内容 | 依赖 |
|------|------|------|
| **A. 接 OpenClaw** | 将 Control 改为 OpenClaw 双 agent；Governance 改为 Plugin（before/after_tool_call）；审批对接 exec.approval；Dashboard/Commander 经 Gateway WS/RPC | OpenClaw 可用环境、Gateway 协议稳定 |
| **B. 深化闭环（仍不接 OpenClaw）** | IM Bot **飞书先行**，钉钉/Discord 等预留接口；对接当前 FastAPI 审批 API；复盘→策略建议或自动调参；Limb 实装（如 Content 接真实发布 API） | 飞书集成测试所需见 [FEISHU-INTEGRATION.md](FEISHU-INTEGRATION.md) |

### 下一步规划（当前）

- **Phase 3 收尾已完成**：回放 UI、可收敛小步、监控扩展、告警渠道 Webhook 均已完成。
- **IM 预留接口已完成**：IMNotifier、get_notifier、FeishuNotifier stub；审批挂起时可选调用 send_approval_request。**飞书实装**：接 Webhook 或发消息 API、解析用户审批指令（事件订阅）待做；所需见 [FEISHU-INTEGRATION.md](FEISHU-INTEGRATION.md)。
- **OpenClaw**：仍在准备中，暂不列入近期必做；准备就绪后再按 Roadmap 方向 A 排期。
- **之后可选**：可收敛扩展（写回 config/自动调参）等；Dashboard 已展示 GET /convergence/suggestions。
