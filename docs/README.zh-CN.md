# claw-assistant 架构说明

**Human-in-the-Loop AI 执行与治理系统**

---

## 一、核心架构概览

claw-assistant 采用四层架构：**人类指挥官**（决策与风险）、**云端大脑**（策略与意图）、**治理中台**（鉴权与审计）、**本地执行集群**（肢体与工具）。人类负责「战略 + 风险 + 观察」，AI 负责「候选方案生成 + 执行 + 提案进化」。

---

## 二、四层架构详解

### 1️⃣ 人类指挥官（Human Judgment Plane）

- **角色**：最终主权、战略和风险控制中心
- **职责**：审批高风险任务、决定行为边界、一键冻结/抢占任务、观察全局态势（系统态 / 任务态 / 世界态）
- **痛点**：作为「指挥官」最怕被频繁打扰（Notification Fatigue）

**优化方案**

- **批处理决策**：低风险任务自动执行并汇总周报。
- **紧急抢占**：通过 IM Bot 实时推送，支持语音回复（如微信语音转文字作为审批指令）。
- **态势看板**：Dashboard 提供「时间轴回放」，可查看过去 24 小时 AI 的思考、执行与卡点。

**交互方式**

- 移动端：IM Bot（飞书 / Telegram / 微信）
- 全息看板：Dashboard（系统态 + 世界态可视化）

**抽象**：HOTL（Human Over The Loop）— 悬在系统上方，不阻塞执行。

---

### 2️⃣ 云端大脑（Control Plane）

- **角色**：策略生成与意图拆解中心
- **组成**：Brain-A（生产脑，稳定业务）、Brain-B（实验脑，影子测试/新协议验证）

**核心机制**

- 多模态意图识别
- 长短期记忆管理（Session 外部化于 Redis/DB）
- 候选任务生成（等待人类审批或直接派发）

**抽象**：AI 策略引擎，但无最终裁决权。

---

### 3️⃣ 治理中台（Governance Plane）

- **角色**：系统免疫与安全过滤器
- **职责**：能力鉴权、任务拦截与挂起、世界确认（World Checkpoint）、幂等校验、协议转换（云端意图 → MCP / OpenClaw）

**世界确认（World Checkpoint）**

- Brain 发出指令（如：粉丝数 +100）→ Limb 执行 → Governance 延时（如 1 小时后）通过 API 抓取真实数据。
- 若现实与预期不符，自动触发「复盘任务」，将失败原因写回 Brain-A 长期记忆。

**意图审查（Constitution）**

- Proxy 维护《宪法》；若 Brain 任务意图偏离设定（如：本应剪辑视频却试图删除素材），自动 `SIGSTOP` 并标记「意图异常」，强制人类介入。

**抽象**：交感神经 + 免疫防火墙，保证外界安全与可审计。

---

### 4️⃣ 本地执行集群（Data Plane）

- **角色**：肌肉与工具箱
- **类型**：运维肢体（部署/监控/修复）、内容肢体（剪辑/渲染/发布）、进化肢体（沙箱新插件、自动生成技能）

**抽象**：物理副作用的执行者，AI 的「手脚」。

---

## 三、核心机制

### 神经系统：SSH 隧道集群

- **反向隧道**：本地主动连云端（10001 → Brain-A, 20001 → Brain-B）。
- **流量调度**：云端调本地如 localhost，高可控、低延迟。

### 任务抢占

- **AI 自行运作**：低优先级任务自动执行。
- **人类插手**：可实时抢占，SIGSTOP / 优先调度。

### 业务与系统进化闭环

- **业务**：本地 Limb 新插件 → Brain-B 影子测试 → 人观察 → Brain-A 正式路由。
- **系统**：Brain-B 新架构 → 小比例流量试验 → 人观察 → Nginx 权重切换。

---

## 四、决策闭环

| 问题 | 机制 |
|------|------|
| **Should We Act?** | AI 生成候选任务 → 标注风险等级 → 高风险挂起 → 人类审批 |
| **How Far Can We Go?** | 策略边界由人配置 → Brain 在边界内自主行动 |
| **Should We Freeze?** | 错误率/世界态异常 → 人类一键冻结或重排优先级 |
| **观察与态势** | 系统态（算力、负载）、任务态（进度、阻塞）、世界态（平台反馈、真实流量） |

---

## 五、Minimal Implementation 示例

### 任务路由配置 `Proxy_Config.json`

```json
{
  "skills": {
    "video_edit": {
      "endpoint": "http://localhost:10002",
      "require_approval": false,
      "priority": 5
    },
    "publish_content": {
      "endpoint": "http://localhost:10002/publish",
      "require_approval": true,
      "checkpoint": "check_platform_api"
    }
  }
}
```

### 任务审批流（伪代码）

```python
def handle_task(task):
    if task.requires_approval():
        notify_human(task.summary)   # 飞书/微信
        status = wait_for_human_click()
        if status == 'REJECT':
            return cancel_task()
    return dispatch_to_limb(task)
```

---

## 六、系统核心价值

| 维度 | 说明 |
|------|------|
| **安全性** | 人类主权 + Proxy 审计 + World Checkpoint |
| **可演进性** | Brain-B 影子测试 + Limb 插件自动注册 |
| **高可控性** | SSH 隧道 + 优先级抢占 + Kill Switch |
| **规模化** | 云端/本地分离 + MCP 标准协议 + 并行执行者 |
| **可观测性** | Dashboard 三种态势 + 决策可回放 |

---

## 七、典型使用节奏

| 时段 | 动作 |
|------|------|
| **早晨** | 看 Dashboard，确认自动运维/发帖情况 |
| **中午** | 收到插件并网请求 → 批准/拒绝 |
| **下午** | 灵感触发 → 发指令/任务 → 系统调度 Limb 完成 |
| **风险发生** | 即时冻结任务或重排优先级 |

**一句话**：人类负责「战略 + 风险 + 观察」，AI 负责「候选方案生成 + 执行 + 提案进化」。

---

## 八、快速开始

（根据实际仓库实现补充：安装、配置、启动命令等。）

---

[← 返回项目首页](../README.md) · [English](README.en.md)
