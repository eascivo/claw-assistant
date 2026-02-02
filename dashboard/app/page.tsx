"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

interface PendingItem {
  approval_id: string;
  task_id: string;
  tool_name: string;
  summary: string;
  risk?: string;
}

interface TimelineEvent {
  ts: number;
  type: string;
  payload: Record<string, unknown>;
}

interface PostmortemItem {
  tool_name: string;
  task_id: string;
  expected: number;
  actual: number;
  deviation: number;
}

export default function DashboardPage() {
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [postmortems, setPostmortems] = useState<PostmortemItem[]>([]);
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const eventsUrl = selectedTaskId
      ? `${API_BASE}/events?task_id=${encodeURIComponent(selectedTaskId)}&limit=100`
      : `${API_BASE}/events?limit=100`;
    try {
      const [statusRes, eventsRes, postmortemsRes] = await Promise.all([
        fetch(`${API_BASE}/status`),
        fetch(eventsUrl),
        fetch(`${API_BASE}/postmortems`),
      ]);
      if (!statusRes.ok) throw new Error(`status: ${statusRes.status}`);
      if (!eventsRes.ok) throw new Error(`events: ${eventsRes.status}`);
      if (!postmortemsRes.ok) throw new Error(`postmortems: ${postmortemsRes.status}`);
      const statusData = await statusRes.json();
      const eventsData = await eventsRes.json();
      const postmortemsData = await postmortemsRes.json();
      const eventList = eventsData.events ?? [];
      setPending(statusData.pending ?? []);
      setEvents(eventList);
      setPostmortems(postmortemsData.postmortems ?? []);
      if (!selectedTaskId) {
        const ids = [...new Set(eventList.map((e: TimelineEvent) => e.payload?.task_id).filter(Boolean) as string[])];
        setTaskIds(ids);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败";
      if (msg === "Failed to fetch" || msg.includes("fetch")) {
        setError(`无法连接 API。请先启动 daemon：claw-assistant serve（默认 ${API_BASE}）`);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 5000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const formatTs = (ts: number) => new Date(ts * 1000).toLocaleString("zh-CN");
  const typeLabel: Record<string, string> = {
    approval_requested: "待审批",
    approval_resolved: "审批结果",
    limb_executed: "Limb 执行",
    postmortem: "复盘",
  };

  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-slate-800 mb-2">claw-assistant 态势看板</h1>
      <p className="text-slate-500 text-sm mb-2">
        待审批、时间轴、复盘 · API: {API_BASE}
        {error && <span className="ml-2 text-red-600">· 连接失败</span>}
        {!error && !loading && <span className="ml-2 text-emerald-600">· 连接正常</span>}
        {!error && loading && <span className="ml-2 text-slate-400">· 检查中…</span>}
      </p>
      <p className="text-slate-400 text-xs mb-4">每 5 秒自动刷新</p>
      <button
        type="button"
        onClick={fetchAll}
        disabled={loading}
        className="mb-6 px-4 py-2 bg-slate-700 text-white rounded hover:bg-slate-600 disabled:opacity-50"
      >
        {loading ? "加载中…" : "刷新"}
      </button>
      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded text-sm">
          <p className="font-medium">{error}</p>
          <p className="mt-1 text-slate-500 text-xs">
            在项目根目录执行：<code className="bg-slate-200 px-1 rounded">claw-assistant serve</code>
          </p>
        </div>
      )}

      <section className="mb-8">
        <h2 className="text-lg font-medium text-slate-700 mb-3">待审批</h2>
        {pending.length === 0 ? (
          <p className="text-slate-500 text-sm">无待审批</p>
        ) : (
          <ul className="space-y-2">
            {pending.map((p) => (
              <li
                key={p.approval_id}
                className="p-3 bg-amber-50 border border-amber-200 rounded text-sm"
              >
                <span className="font-mono text-xs text-slate-500">{p.approval_id}</span>
                <span className="ml-2">{p.tool_name}</span>
                <span className="ml-2 text-slate-600">{p.summary?.slice(0, 60)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h2 className="text-lg font-medium text-slate-700">时间轴（最近 100 条）</h2>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            按任务回放
            <select
              value={selectedTaskId ?? ""}
              onChange={(e) => setSelectedTaskId(e.target.value ? e.target.value : null)}
              className="border border-slate-300 rounded px-2 py-1 bg-white text-slate-800"
            >
              <option value="">全部</option>
              {taskIds.map((id) => (
                <option key={id} value={id}>
                  {id.slice(0, 8)}…
                </option>
              ))}
            </select>
          </label>
        </div>
        {events.length === 0 ? (
          <p className="text-slate-500 text-sm">暂无事件</p>
        ) : (
          <ul className="space-y-2">
            {[...events].reverse().map((e, i) => (
              <li
                key={`${e.ts}-${i}`}
                className="p-3 bg-white border border-slate-200 rounded text-sm flex gap-3"
              >
                <span className="text-slate-400 shrink-0">{formatTs(e.ts)}</span>
                <span className="font-medium shrink-0">{typeLabel[e.type] ?? e.type}</span>
                <span className="text-slate-600 truncate">
                  {JSON.stringify(e.payload).slice(0, 80)}…
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-lg font-medium text-slate-700 mb-3">复盘（World Checkpoint）</h2>
        {postmortems.length === 0 ? (
          <p className="text-slate-500 text-sm">暂无复盘</p>
        ) : (
          <ul className="space-y-2">
            {postmortems.map((pm, i) => (
              <li
                key={`${pm.task_id}-${i}`}
                className="p-3 bg-red-50 border border-red-200 rounded text-sm"
              >
                <span>{pm.tool_name}</span>
                <span className="ml-2 font-mono text-xs">{pm.task_id}</span>
                <span className="ml-2">
                  期望 {pm.expected} 实际 {pm.actual} 偏差 {(pm.deviation * 100).toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
