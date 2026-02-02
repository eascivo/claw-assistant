# claw-assistant Architecture

**Human-in-the-Loop AI Execution & Governance System**

---

## 1. Core Architecture Overview

claw-assistant uses a four-plane architecture: **The Commander** (decision & risk), **Double Brain** (strategy & intent), **Governance Plane** (auth & audit), and **Multi-Limbs** (execution & tools). Humans own strategy, risk, and observation; AI owns candidate generation, execution, and evolution.

---

## 2. The Four Planes

### 1️⃣ The Commander (Human Judgment Plane)

- **Role**: Ultimate sovereignty, strategy, and risk control
- **Duties**: Approve high-risk tasks, set behavior bounds, freeze/priority override, observe system/task/world state
- **Pain**: Commanders suffer from notification fatigue

**Optimizations**

- **Batched decisions**: Low-stakes tasks auto-run with weekly summaries.
- **Emergency override**: IM Bot push with voice-reply approval (e.g. WeChat voice → text as command).
- **Situation dashboard**: Timeline replay of what AI thought, did, and where it got stuck in the last 24h.

**Interaction**

- **Mobile**: IM Bot (Lark / Telegram / WeChat)
- **Dashboard**: Full view of system state and world state

**Abstract**: HOTL — human over the loop, not blocking execution.

---

### 2️⃣ Double Brain (Control Plane)

- **Role**: Strategy generation and intent decomposition
- **Components**: Brain-A (production), Brain-B (experimental / shadow testing)

**Core Mechanisms**

- Multimodal intent recognition
- Long/short-term memory (sessions externalized in Redis/DB)
- Candidate task generation (await human approval or direct dispatch)

**Abstract**: AI strategy engine without final authority.

---

### 3️⃣ Agent Proxy (Governance Plane)

- **Role**: System immunity and safety filter
- **Duties**: Capability auth, task intercept/suspend, world checkpoint, idempotency, protocol translation (cloud intent → MCP/OpenClaw)

**World Checkpoint**

- Brain issues command (e.g. +100 followers) → Limb executes → Governance fetches real data via API after delay (e.g. 1h).
- If reality diverges from expectation, auto-trigger “post-mortem” and write failure reason back to Brain-A long-term memory.

**Intent Review (Constitution)**

- Proxy maintains a Constitution; if Brain task intent deviates (e.g. should edit video but tries to delete assets), auto `SIGSTOP` and mark “intent anomaly”, forcing human intervention.

**Abstract**: Sympathetic nervous system + immune firewall for safety and auditability.

---

### 4️⃣ Multi-Limbs (Data Plane)

- **Role**: Muscles and tooling
- **Types**: Ops limbs (deploy/monitor/fix), content limbs (edit/render/publish), evolution limbs (sandbox plugins, auto-generated skills)

**Abstract**: Executors of physical side effects; AI’s “hands and feet”.

---

## 3. Core Mechanisms

### Nervous System: SSH Tunnel Cluster

- **Reverse tunnel**: Local initiates to cloud (10001 → Brain-A, 20001 → Brain-B).
- **Traffic routing**: Cloud calls local as localhost; high control, low latency.

### Task Preemption

- **Auto-run**: Low-priority tasks execute automatically.
- **Human override**: Real-time preemption, SIGSTOP / priority scheduling.

### Business & System Evolution Loop

- **Business**: New Limb plugin → Brain-B shadow test → human review → Brain-A production route.
- **System**: Brain-B new architecture → canary → human review → Nginx weight switch.

---

## 4. Decision Loops

| Question | Mechanism |
|----------|-----------|
| **Should We Act?** | AI generates candidate tasks → risk tagging → high-risk held → human approval |
| **How Far Can We Go?** | Bounds set by human → Brain acts within bounds |
| **Should We Freeze?** | Error rate / world-state anomaly → human freeze or reprioritize |
| **Observation** | System state (compute, load), task state (progress, block), world state (platform feedback, real traffic) |

---

## 5. Minimal Implementation Example

### Task routing config `Proxy_Config.json`

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

### Approval flow (pseudo-code)

```python
def handle_task(task):
    if task.requires_approval():
        notify_human(task.summary)
        status = wait_for_human_click()
        if status == 'REJECT':
            return cancel_task()
    return dispatch_to_limb(task)
```

---

## 6. Core Value Proposition

| Dimension | Description |
|-----------|-------------|
| **Security** | Human sovereignty + Proxy audit + World Checkpoint |
| **Evolvability** | Brain-B shadow test + Limb plugin auto-registration |
| **Control** | SSH tunnel + priority preemption + Kill Switch |
| **Scale** | Cloud/local separation + MCP standard + parallel executors |
| **Observability** | Dashboard (three states) + decision replay |

---

## 7. Your Role (Typical Day)

| Time | Action |
|------|--------|
| **Morning** | Check dashboard, confirm auto-ops / posting |
| **Noon** | Plugin merge request → approve / reject |
| **Afternoon** | Idea → send command/task → system dispatches Limb |
| **Incident** | Freeze task or reprioritize |

**In one line**: Humans own strategy, risk, and observation; AI owns candidate generation, execution, and evolution.

---

## 8. Quick Start

(To be filled with install, config, and run commands as the repo is implemented.)

---

[← Back to project](../README.md) · [中文](README.zh-CN.md)
