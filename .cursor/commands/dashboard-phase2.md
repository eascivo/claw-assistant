# 做 Phase 2：Dashboard 时间轴

按 **docs/IMPLEMENTATION-PATH.md** 中 Phase 2 的「Dashboard 时间轴」条目执行：

1. **事件存储**：定义事件模型（审批 requested/resolved、limb 执行、postmortem）；实现存储（内存或 SQLite），Daemon 在审批/执行/复盘时写入事件。
2. **API**：FastAPI 暴露读事件接口（如 GET /events?since=… 或按时间轴聚合）。
3. **前端**：Next.js + Tailwind，连接后端 API，展示待审批、任务列表、24h 决策回放时间轴、postmortems。

遵守开发流程（测试先行、小步开发）、语言偏好（后端 Python、前端 TypeScript）。完成后更新 IMPLEMENTATION-PATH 的下一步规划并提交推送。

现在开始执行。
