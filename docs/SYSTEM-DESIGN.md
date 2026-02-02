# claw-assistant 系统设计（Technical Design v1.0）

**HOTL 主权 AI 执行系统：组件选型、OpenClaw 使用边界、交互协议与伪代码**

---

## 目标（一句话）

构建一个 **HOTL（Human Over The Loop）主权 AI 执行系统**：在「人类掌控边界」的前提下，实现 **多脑决策 + 治理审计 + 本地执行集群** 的可扩展自动化，最终服务于可控的规模化收益（100W/年）。

---

## 一、总体架构与数据流

```
┌──────────────── Commander Plane ────────────────┐
│ 人类指挥官（IM Bot / Dashboard）                 │
│ 审批 / 冻结 / 参数修改 / 态势感知 / 决策回放     │
└───────────────▲───────────────────────────────┘
                │ HOTL（非阻塞）
┌───────────────┴───────────────────────────────┐
│ Control Plane · Double Brain                    │
│ Brain-A（稳定执行） | Brain-B（实验影子）        │
│ 意图识别 / 策略生成 / 候选任务 & 风险标注         │
└───────────────▲───────────────────────────────┘
                │ Intent / Task
┌───────────────┴───────────────────────────────┐
│ Governance Plane · Agent Proxy                  │
│ 权限 / 宪法 / 幂等 / 世界态校验 / SIGSTOP       │
└───────────────▲───────────────────────────────┘
                │ MCP / OpenClaw 协议
┌───────────────┴───────────────────────────────┐
│ Data Plane · Multi-Limbs                        │
│ Ops / Content / Dev / Sandbox · 本地执行        │
└────────────────────────────────────────────────┘
```

**核心任务流**：`Intent → Task → Proxy Audit → Approval? → Limb → World Check → Memory`

---

## 二、组件选型总表

| 层级 | 组件 | 技术选型 | 与 OpenClaw 关系 |
|------|------|----------|-------------------|
| **Commander** | IM Bot | 飞书 Bot API / Telegram Bot API / 微信（Webhook → Proxy） | 通过 **commander** agent 的 channel 绑定，用 `sessions_send` 收发明文/结构化指令 |
| **Commander** | Dashboard | Next.js + Tailwind（Frontend）+ FastAPI 或 Go（Backend） | 连接 OpenClaw Gateway（WS），调用 `health`、`system-presence`、`exec.approval.*`、自定义 RPC（若有）；可选复用 Control UI |
| **Control** | Brain-A / Brain-B | OpenClaw 多 agent（main / experimental） | **完全基于 OpenClaw**：agent 运行时、workspace、session、bindings |
| **Governance** | Proxy（宪法/审批/幂等/World Check） | OpenClaw **Plugin**（hooks + 可选独立服务） | **寄生在 OpenClaw**：`before_tool_call` / `after_tool_call` / `tool_result_persist`；审批用 `exec.approval.request` / `exec.approval.resolve` 或扩展 RPC |
| **Data** | Limbs | OpenClaw **tools**（exec / nodes / skills）+ 本地 MCP/HTTP 服务 | **通过 OpenClaw**：工具注册在 agent workspace；本地 Limb 经 **SSH 反向隧道** 或 **Node** 连到 Gateway，对云端等同 localhost |

**结论**：  
- **Commander**：外部产品（IM + Dashboard），通过 OpenClaw Gateway 的 **WS + RPC** 与「指挥官 agent」和「审批/态势」交互。  
- **Control**：**全部用 OpenClaw**（双 agent = Brain-A/B）。  
- **Governance**：**全部用 OpenClaw**（Plugin hooks + exec 审批 + 可选 Constitution 服务）。  
- **Data**：**用 OpenClaw 调工具**；Limb 本体可以是本地进程（OpenClaw Node 或独立 MCP Server），经隧道暴露给 Gateway。

---

## 三、OpenClaw 使用边界（哪里用、怎么用）

### 3.1 Control Plane（双脑）—— 全部用 OpenClaw

- **Brain-A**：对应 OpenClaw 的 `agents.list[]` 中 `id: "main"`, `default: true`，绑定主渠道（如 WhatsApp、主 Telegram）。
- **Brain-B**：对应 `id: "experimental"`，绑定实验渠道（如 WebChat、单独群）。
- **意图识别 / 任务生成**：由各 agent 的 **模型 + workspace 内 system prompt / skills** 完成；输出「候选工具调用」与参数，不直接输出 TASK_ID，由 Governance 层在 `before_tool_call` 里映射为「任务」并打风险标签。
- **记忆**：  
  - 短期：OpenClaw 自带的 **Session**（`~/.openclaw/agents/<agentId>/sessions`）。  
  - 长期：可选 **Redis/DB**，通过 `tool_result_persist` 或独立 Job 写「任务结果、失败原因」；向量库由外部服务提供，Brain 通过 **Skill/工具** 调用。

**不在 OpenClaw 里实现的**：IntentGraph、风险等级计算、expected_roi 等「业务元数据」—— 可在 Plugin 或 Dashboard 后端根据「工具名 + 参数」推导并存储。

### 3.2 Governance Plane（Proxy）—— 全部用 OpenClaw 能力扩展

- **能力鉴权**：OpenClaw 已有 `tools.allow` / `tools.deny`、`tools.exec.security`（allowlist 等）；Limb 白名单用 **claw-assistant 配置**（如 `claw.proxy.limbs`）在 Plugin 里与 `before_tool_call` 结合使用。
- **任务拦截与挂起**：  
  - **exec 类**：直接用 OpenClaw 的 `tools.exec.ask`（always / on-miss）与 `exec.approval.request` / `exec.approval.resolve`。  
  - **自定义高风险工具**（如 `publish_content`）：在 **Plugin `before_tool_call`** 里判断；若需人工审批，则调用内部「审批管理器」挂起（见下交互协议），再通过 commander 渠道或 Dashboard 等待 `exec.approval.resolve` 或自定义 RPC 回调。
- **宪法（Constitution）**：  
  - 规则存 **YAML/JSON**（如 `constitution.rules`）；在 `before_tool_call` 里用 **LLM 或规则引擎** 算 Intent Deviation Score，超过阈值则 `return { block: true, blockReason: "constitution" }`，并可选发事件给 Commander。
- **幂等**：OpenClaw 的 `idempotencyKey`（send / agent）继续用；Limb 执行侧由 Proxy 在派发前生成 **Task Hash**，写入 Store，在 `before_tool_call` 或工具参数里带去重。
- **World Checkpoint**：在 **`after_tool_call`** 或 **`tool_result_persist`** 里根据 `toolName` 调用「校验器」（如调平台 API 拉真实粉丝数）；若与预期不符，写回「复盘任务」到长期记忆并可选通知 Commander。

以上全部是 **OpenClaw Plugin hooks + 配置 + 可选外部服务**，不 fork OpenClaw。

### 3.3 Commander Plane —— 通过 OpenClaw Gateway 交互

- **IM Bot**：  
  - 飞书/Telegram/微信 收到用户指令 → Bot 后端解析（如 `/approve TASK_ID`）→ 通过 **OpenClaw Gateway** 调用：  
    - `sessions_send` 向 **commander** agent 的 session 发结构化消息（供内部消费），或  
    - 自定义 RPC（如 `claw.approval.resolve`）若在 Gateway 上扩展；否则通过 **exec.approval.resolve** 解挂「挂起的高风险工具」审批。  
  - 审批请求：Governance Plugin 在挂起时通过 `sessions_send` 或 **send** 向 commander 绑定 channel 发消息（卡片/链接），人类回复后 Bot 调 `exec.approval.resolve` 或等价 RPC。
- **Dashboard**：  
  - 连接同一 OpenClaw Gateway（WS），调用：  
    - `health`、`system-presence` → **系统态**；  
    - `exec.approvals.get`、exec 审批事件 → **任务态**；  
    - 自建「世界态」接口（由 Governance 或独立服务在 checkpoint 后写入 DB，Dashboard 读 API）。  
  - 时间轴回放：Event Sourcing 数据来自「会话 transcript + 审批事件」；Dashboard 后端从 OpenClaw 的 session transcript 或自建事件表聚合。

### 3.4 Data Plane（Limbs）—— 通过 OpenClaw 调度，本体可在本地

- **Limb 形态**：  
  - **运维**：OpenClaw 自带 **exec**、**cron**、**nodes**（远程执行）。  
  - **内容/发布**：通过 **Skill** 或 **HTTP Tool** 注册到 agent workspace，实际请求发到本地或远程 HTTP/MCP；若本地，则用 **SSH 反向隧道**（本地 `ssh -R 10001:localhost:8080 cloud`）或 **OpenClaw Node** 暴露给 Gateway。  
  - **进化**：Sandbox agent 或 experimental workspace 的 skills 先试，再推广到 main。
- **协议**：  
  - 云端到 Limb：**OpenClaw 标准工具调用**（Gateway → agent 运行时 → tool invoke）；Limb 为 HTTP 时即 REST；为 MCP 时由 OpenClaw 的 MCP 客户端（若有）或 HTTP 包装调用。  
  - 不在 OpenClaw 内的「自定义协议」仅限 Limb 内部实现（如剪辑引擎的 API），对上游统一为「工具调用 + 参数」。

---

## 四、交互协议（详细）

### 4.1 Commander ↔ OpenClaw（Gateway）

- **认证**：与 OpenClaw 一致，`connect.params.auth.token`（或 password）。
- **审批解析**：  
  - 人类在 IM 发 `/approve <approval_id>` 或点击 Dashboard 按钮 → 调用 `exec.approval.resolve`，参数 `{ id, decision: "allow-once" | "deny" | ... }`。  
  - 若 claw-assistant 扩展了「任务级审批」（非 exec），可增加 RPC 如 `claw.task.approval.resolve`，参数 `{ taskId, decision, params? }`，由 Plugin 或独立服务实现并注册到 Gateway。
- **冻结**：  
  - 发 `/stop` 到 commander 会话 → 后端解析后调 OpenClaw 的 **chat.abort**（或等价）中止当前 run；  
  - 或通过 Dashboard 调同一接口。  
  - 锁 API Key/Token：在 **Governance 或 Dashboard 后端** 维护「禁用列表」，Proxy 在 `before_tool_call` 里拒绝带该 Key 的调用；不一定要 OpenClaw 原生支持。
- **态势**：  
  - 系统态：`health`、`system-presence`；  
  - 任务态：`exec.approvals.get`、事件 `exec.approval.requested` / `exec.approval.resolved`；  
  - 世界态：自建 API（Governance 写 checkpoint 结果到 DB，Dashboard 读）。

### 4.2 Control（Brain-A/B）↔ Governance（Proxy）

- 无显式 RPC：Brain 只「发起工具调用」；Proxy 在 **before_tool_call** 里拦截。  
- **约定**：  
  - 工具名与 `claw.proxy.limbs` 配置一致（如 `publish_content`）；  
  - 参数可带 `taskId`、`idempotencyKey`、`expectedWorldState`（供 World Checkpoint 用）。  
- **before_tool_call 返回**：  
  - `{ block: false, params }`：放行，可改参数；  
  - `{ block: true, blockReason }`：拒绝，不执行工具。

### 4.3 Governance ↔ Commander（审批挂起与解挂）

- **挂起**：Plugin 在 `before_tool_call` 里发现需审批 → 调用内部 **ApprovalManager**（内存或 Redis）生成 `approvalId`，通过 `sessions_send` 或 **send** 向 commander channel 发「待审批」消息（含 approvalId、摘要）；然后 **挂起当前 run**（或挂起该 tool call 的 Promise），直到收到 resolve。
- **解挂**：  
  - 方案 A：统一用 OpenClaw 的 `exec.approval.request` 把「自定义任务」也映射成一次「虚拟 exec」审批，Commander 点批准后调 `exec.approval.resolve`。  
  - 方案 B：自定义 `claw.approval.request` / `claw.approval.resolve`，Gateway 上注册方法，Plugin 在挂起时发 request 事件，Commander 调 resolve 解挂。  
- **协议格式**（示例）：  
  - request：`{ approvalId, taskId?, toolName, summary, risk?, expiresAt }`；  
  - resolve：`{ approvalId, decision: "approve" | "reject", params? }`。

### 4.4 Governance ↔ Data（Limb）

- 通过 OpenClaw 的 **工具调用** 下发；Governance 不直连 Limb，只「放行或拒绝」工具调用。  
- 若 Limb 是 **HTTP**：agent 的 tool 定义里写清楚 URL（可为隧道内 localhost）；若 Limb 是 **Node**：OpenClaw 的 `node.invoke` 已定义协议，按现有文档即可。

### 4.5 World Checkpoint 与记忆回写

- **触发**：`after_tool_call` 或 `tool_result_persist` 中，根据 `toolName` 和配置的 `checkpoint` 名，调用「校验器」（如请求平台 API 获取真实粉丝数）。  
- **输入**：工具结果 + 调用前的 `expectedWorldState`（可从 session 或 Store 取）。  
- **输出**：偏差度（如 -88%）；若超过阈值，则：  
  - 写「复盘任务」到长期记忆（DB/向量库）；  
  - 可选推事件给 Commander（Dashboard / IM）。  
- **协议**：内部接口即可；例如 `checkpoint.run({ toolName, taskId, expected, actual }) -> { deviation, triggered }`。

---

## 五、各层伪代码

### 5.1 任务流（Governance 主控）

```text
FUNCTION runTaskFlow(intent, context):
  task = Brain.generateTask(intent, context)           // Brain-A 或 B 产出候选工具调用
  IF Constitution.check(task) BLOCKED THEN
    NOTIFY Commander("constitution", task)
    RETURN
  IF Proxy.requiresApproval(task) THEN
    approvalId = ApprovalManager.suspend(task)
    NOTIFY Commander(approvalId, task.summary)
    decision = AWAIT ApprovalManager.wait(approvalId, timeout)
    IF decision = "reject" THEN RETURN
  IF NOT Idempotency.check(task.hash) THEN RETURN      // 已执行过
  result = Limb.execute(task)                          // 通过 OpenClaw 工具调用
  WorldCheckpoint.schedule(task, result, delay)         // 延时校验
  Idempotency.record(task.hash)
  IF WorldCheckpoint.deviation HIGH THEN
    Memory.writePostmortem(task, actual, expected)
    NOTIFY Commander("world_deviation", task)
  RETURN result
```

### 5.2 审批挂起（Plugin before_tool_call）

```text
HOOK before_tool_call(event, ctx):
  limb = config.limbs[event.toolName]
  IF limb IS NULL THEN RETURN { block: false }
  IF Constitution.violation(event.toolName, event.params) THEN
    RETURN { block: true, blockReason: "constitution" }
  IF limb.require_approval THEN
    approvalId = generateId()
    ApprovalManager.register(approvalId, ctx.sessionKey, event)
    sendToCommander({ approvalId, summary: event.params.summary, risk: limb.risk })
    decision = AWAIT ApprovalManager.wait(approvalId)
    IF decision = "reject" THEN RETURN { block: true, blockReason: "rejected" }
  RETURN { block: false, params: event.params }
```

### 5.3 Constitution 引擎

```text
CONSTITUTION RULES (YAML):
  forbid: [ "delete_user_data" ]
  allow: [ "video_edit" ]
  restrict:
    - action: "trading"
      require_human: true

FUNCTION check(task):
  IF task.action IN rules.forbid THEN RETURN BLOCKED
  IF task.action IN rules.restrict AND NOT task.human_approved THEN RETURN BLOCKED
  deviationScore = LLM.intentDeviation(task.intent, task.params)  // 可选
  IF deviationScore > threshold THEN RETURN BLOCKED
  RETURN ALLOWED
```

### 5.4 World Checkpoint

```text
FUNCTION schedule(task, result, delay):
  SET_TIMEOUT(delay, () => {
    actual = FetchFromWorld(task.metric)    // 如平台 API 粉丝数
    expected = task.expectedWorldState
    deviation = (actual - expected) / expected
    IF ABS(deviation) > threshold THEN
      Memory.writePostmortem(task, actual, expected)
      Broadcast("world_deviation", { taskId: task.id, deviation })
  })
```

### 5.5 Commander 指令解析（IM Bot）

```text
ON message FROM user:
  IF message = "/approve <id>" THEN
    CALL Gateway.exec.approval.resolve({ id, decision: "allow-once" })
  IF message = "/reject <id>" THEN
    CALL Gateway.exec.approval.resolve({ id, decision: "deny" })
  IF message = "/freeze limb=<name>" THEN
    Proxy.freezeLimb(name)   // 写配置或 DB，before_tool_call 里拒绝该 limb
  IF message = "/stop" THEN
    CALL Gateway.chat.abort({ sessionKey: commanderSession })
```

---

## 六、MVP 落地路径（与初稿对齐）

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **Phase 1（约 2 周）** | 单 Brain-A；单 Limb（Content）；Proxy + 人工审批；World Checkpoint（粉丝/收益） | OpenClaw 单 agent、Plugin（before_tool_call + exec 审批）、commander channel |
| **Phase 2** | Brain-B 影子测试；Constitution v1；Dashboard 时间轴 | 双 agent bindings、Constitution 规则 + before_tool_call、事件存储 |
| **Phase 3** | 多 Limb；自动复盘；商业闭环稳定 | 多 tools/skills、World Checkpoint 回写、收益指标与告警 |

---

## 七、小结

- **组件**：Commander = IM Bot + Dashboard（外部）；Control = OpenClaw 双 agent；Governance = OpenClaw Plugin + exec 审批 + 可选 Constitution/Approval 服务；Data = OpenClaw tools + Nodes + 本地 Limb（隧道/MCP）。  
- **OpenClaw 使用点**：双脑（agent）、会话与记忆入口、所有工具调度、exec 审批、before/after_tool_call 与 tool_result_persist、Gateway 的 WS/RPC（含 health、send、sessions、approval）。  
- **交互协议**：Commander 通过 Gateway 的 `exec.approval.resolve`、`chat.abort`、`health`、`sessions_send` 等与系统交互；Governance 与 Brain 通过「工具调用 + hooks」交互；与 Limb 通过 OpenClaw 工具调用与 Node 协议。  
- **其余逻辑**：Constitution、Task 级审批、World Checkpoint、复盘回写，均以 **伪代码 + 配置** 形式在上述位置接入，无需改 OpenClaw 核心。

此设计可直接作为「初版实现清单」与评审依据；详细代码可依此拆分为 Plugin、Dashboard 后端、IM Bot、Constitution/Checkpoint 服务等子项迭代实现。

---

## 附录 A：OpenClaw 使用点速查

| 能力 | 使用位置 | OpenClaw 能力 |
|------|----------|----------------|
| 双脑运行时 | Control Plane | `agents.list`（main / experimental）、bindings、workspace |
| 会话与短期记忆 | Control / Commander | Session 存储、`sessions_send`、transcript |
| 工具调度 | Data Plane | tools、exec、nodes、skills、HTTP tools |
| 审批 | Governance ↔ Commander | `exec.approval.request` / `exec.approval.resolve`、事件 `exec.approval.requested` / `resolved` |
| 任务拦截 | Governance | Plugin `before_tool_call`（block / 挂起） |
| 宪法/意图 | Governance | Plugin `before_tool_call` 内调 Constitution 服务或规则引擎 |
| 世界校验 | Governance | Plugin `after_tool_call` / `tool_result_persist` 内调 Checkpoint 逻辑 |
| 幂等 | Governance | `idempotencyKey`（send/agent）+ 自建 Task Hash 去重 |
| 冻结/停止 | Commander | `chat.abort`、自建 limb 禁用列表 |
| 态势 | Commander Dashboard | `health`、`system-presence`、`exec.approvals.get`、自建世界态 API |
| 本地 Limb 暴露 | Data Plane | SSH 反向隧道、OpenClaw Node、Gateway 调 localhost |

---

## 附录 B：协议报文示例（参考）

- **exec.approval.request**（OpenClaw 已有）：  
  Request: `{ command, nodeId?, ... }`  
  Response: `{ id, ... }`；随后事件 `exec.approval.requested` 推给有权限客户端。

- **exec.approval.resolve**：  
  Params: `{ id, decision: "allow-once" | "deny" | ... }`  
  解挂后事件 `exec.approval.resolved`。

- **claw-assistant 扩展（若做任务级审批）**：  
  Request: `claw.task.approval.request` → `{ taskId, toolName, summary, risk, expiresAt }`  
  Resolve: `claw.task.approval.resolve` → `{ taskId, decision, params? }`  
  由 Plugin 或 Gateway 扩展实现，Commander 与 Dashboard 调用。
