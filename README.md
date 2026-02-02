# claw-assistant

**Human-in-the-Loop AI 执行与治理系统**  
**Human-in-the-Loop AI Execution & Governance System**

四层架构：人类指挥官 → 云端大脑 → 治理中台 → 本地执行集群。  
Four planes: Commander → Double Brain → Governance → Multi-Limbs.

---

## 本地 MVP 快速开始

当前仓库已实现**最小 MVP**（对齐 [SYSTEM-DESIGN.md](docs/SYSTEM-DESIGN.md) Phase 1）：单 Brain-A、单 Limb（Content）、Proxy + 人工审批、World Checkpoint 占位。技术栈：**Python**（FastAPI + Typer CLI）。

### 依赖

- Python 3.10+
- 配置文件（可选）：将 `config.example.yaml` 复制为 `config.yaml` 后按需修改；不提供则使用内置默认配置。

### 安装与运行

```bash
# 安装（开发模式）
pip install -e .

# 终端 1：启动 daemon
claw-assistant serve
# 或：uvicorn claw_assistant.server.app:create_app --factory --host 0.0.0.0 --port 8080

# 终端 2：发起一次任务（会挂起等待审批）
claw-assistant run "发布一条测试"

# 终端 3：查看待审批、解挂
claw-assistant status
claw-assistant approve <approvalId>
# 或拒绝：claw-assistant reject <approvalId>
```

解挂后，终端 2 会收到执行结果；Content Limb 当前为 stub，仅打 log。

### 子命令

| 命令 | 说明 |
|------|------|
| `serve [--host] [--port]` | 启动本地 HTTP daemon（默认 0.0.0.0:8080） |
| `run <intent>` | 向 daemon 发起一次任务流 |
| `status` | 列出待审批 |
| `approve <id>` | 通过审批 |
| `reject <id>` | 拒绝审批 |

### 测试

```bash
pytest tests/ -v
```

---

## 文档 | Documentation

| 类型 | 文档 |
|------|------|
| **系统设计（组件 / OpenClaw / 协议 / 伪代码）** | [docs/SYSTEM-DESIGN.md](docs/SYSTEM-DESIGN.md) |
| **MVP 实现路径（拆分与目录结构）** | [docs/IMPLEMENTATION-PATH.md](docs/IMPLEMENTATION-PATH.md) |
| **架构说明（中文）** | [docs/README.zh-CN.md](docs/README.zh-CN.md) |
| **Architecture (EN)** | [docs/README.en.md](docs/README.en.md) |

---

## License

（按项目实际情况填写 / Specify as needed.）
