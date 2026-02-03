"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const SECTION_KEYS = ["pending", "timeline", "postmortems", "convergence", "goals"] as const;
const SECTION_LABELS: Record<(typeof SECTION_KEYS)[number], string> = {
  pending: "待审批",
  timeline: "时间轴",
  postmortems: "复盘",
  convergence: "可收敛建议",
  goals: "目标列表",
};
const STORAGE_KEY = "claw-dashboard-sections";

function loadSectionVisibility(): Record<(typeof SECTION_KEYS)[number], boolean> {
  if (typeof window === "undefined") {
    return { pending: true, timeline: true, postmortems: true, convergence: true, goals: true };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, boolean>;
      return {
        pending: parsed.pending !== false,
        timeline: parsed.timeline !== false,
        postmortems: parsed.postmortems !== false,
        convergence: parsed.convergence !== false,
        goals: parsed.goals !== false,
      };
    }
  } catch {
    /* ignore */
  }
  return { pending: true, timeline: true, postmortems: true, convergence: true, goals: true };
}

function saveSectionVisibility(v: Record<(typeof SECTION_KEYS)[number], boolean>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  } catch {
    /* ignore */
  }
}

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

interface SuggestionItem {
  id: string;
  text: string;
  source: string;
}

interface GoalItem {
  id: string;
  text: string;
  status: string;
  created_at: number;
}

export default function DashboardPage() {
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [postmortems, setPostmortems] = useState<PostmortemItem[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sectionVisible, setSectionVisible] = useState<Record<(typeof SECTION_KEYS)[number], boolean>>({
    pending: true,
    timeline: true,
    postmortems: true,
    convergence: true,
    goals: true,
  });
  const [goals, setGoals] = useState<GoalItem[]>([]);
  const [goalsFilter, setGoalsFilter] = useState<string>("");

  useEffect(() => {
    setSectionVisible(loadSectionVisibility());
  }, []);

  const toggleSection = useCallback((key: (typeof SECTION_KEYS)[number]) => {
    setSectionVisible((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      saveSectionVisibility(next);
      return next;
    });
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const eventsUrl = selectedTaskId
      ? `${API_BASE}/events?task_id=${encodeURIComponent(selectedTaskId)}&limit=100`
      : `${API_BASE}/events?limit=100`;
    const goalsUrl = goalsFilter
      ? `${API_BASE}/goals?status=${encodeURIComponent(goalsFilter)}`
      : `${API_BASE}/goals`;
    try {
      const [statusRes, eventsRes, postmortemsRes, suggestionsRes, goalsRes] = await Promise.all([
        fetch(`${API_BASE}/status`),
        fetch(eventsUrl),
        fetch(`${API_BASE}/postmortems`),
        fetch(`${API_BASE}/convergence/suggestions`),
        fetch(goalsUrl),
      ]);
      if (!statusRes.ok) throw new Error(`status: ${statusRes.status}`);
      if (!eventsRes.ok) throw new Error(`events: ${eventsRes.status}`);
      if (!postmortemsRes.ok) throw new Error(`postmortems: ${postmortemsRes.status}`);
      if (!suggestionsRes.ok) throw new Error(`convergence: ${suggestionsRes.status}`);
      if (!goalsRes.ok) throw new Error(`goals: ${goalsRes.status}`);
      const statusData = await statusRes.json();
      const eventsData = await eventsRes.json();
      const postmortemsData = await postmortemsRes.json();
      const suggestionsData = await suggestionsRes.json();
      const goalsData = await goalsRes.json();
      const eventList = eventsData.events ?? [];
      setPending(statusData.pending ?? []);
      setEvents(eventList);
      setPostmortems(postmortemsData.postmortems ?? []);
      setSuggestions((suggestionsData.suggestions ?? []) as SuggestionItem[]);
      setGoals((goalsData.goals ?? []) as GoalItem[]);
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
  }, [selectedTaskId, goalsFilter]);

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
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={fetchAll}
          disabled={loading}
          className="px-4 py-2 bg-slate-700 text-white rounded hover:bg-slate-600 disabled:opacity-50"
        >
          {loading ? "加载中…" : "刷新"}
        </button>
        <span className="text-slate-500 text-sm">显示：</span>
        {SECTION_KEYS.map((key) => (
          <label key={key} className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
            <input
              type="checkbox"
              checked={sectionVisible[key]}
              onChange={() => toggleSection(key)}
              className="rounded border-slate-300"
            />
            {SECTION_LABELS[key]}
          </label>
        ))}
      </div>
      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded text-sm">
          <p className="font-medium">{error}</p>
          <p className="mt-1 text-slate-500 text-xs">
            在项目根目录执行：<code className="bg-slate-200 px-1 rounded">claw-assistant serve</code>
          </p>
        </div>
      )}

      {sectionVisible.pending && (
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
      )}

      {sectionVisible.timeline && (
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
      )}

      {sectionVisible.postmortems && (
      <section className="mb-8">
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
      )}

      {sectionVisible.convergence && (
      <section className="mb-8">
        <h2 className="text-lg font-medium text-slate-700 mb-3">可收敛建议</h2>
        <p className="text-slate-500 text-xs mb-2">基于复盘与告警阈值的策略建议（供人工决策或后续自动调参）</p>
        {suggestions.length === 0 ? (
          <p className="text-slate-500 text-sm">暂无建议</p>
        ) : (
          <ul className="space-y-2">
            {suggestions.map((s) => (
              <li
                key={s.id}
                className="p-3 bg-sky-50 border border-sky-200 rounded text-sm"
              >
                <span className="font-mono text-xs text-slate-500">{s.id}</span>
                <span className="ml-2 text-slate-700">{s.text}</span>
                {s.source && (
                  <span className="ml-2 text-slate-400 text-xs">来源: {s.source}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      )}

      {sectionVisible.goals && (
      <section>
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h2 className="text-lg font-medium text-slate-700">目标列表</h2>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            状态
            <select
              value={goalsFilter}
              onChange={(e) => setGoalsFilter(e.target.value)}
              className="border border-slate-300 rounded px-2 py-1 bg-white text-slate-800"
            >
              <option value="">全部</option>
              <option value="pending">待处理</option>
              <option value="done">已完成</option>
              <option value="cancelled">已取消</option>
            </select>
          </label>
        </div>
        <p className="text-slate-500 text-xs mb-2">目标池（人类偶发设定，后续可拆解为 intent 调用执行）</p>
        {goals.length === 0 ? (
          <p className="text-slate-500 text-sm">暂无目标</p>
        ) : (
          <ul className="space-y-2">
            {goals.map((g) => (
              <li
                key={g.id}
                className="p-3 bg-white border border-slate-200 rounded text-sm flex items-center justify-between gap-3"
              >
                <span className="text-slate-700 flex-1 truncate">{g.text}</span>
                <span
                  className={`shrink-0 text-xs px-2 py-0.5 rounded ${
                    g.status === "done"
                      ? "bg-emerald-100 text-emerald-700"
                      : g.status === "cancelled"
                        ? "bg-slate-100 text-slate-500"
                        : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {g.status === "pending" ? "待处理" : g.status === "done" ? "已完成" : "已取消"}
                </span>
                <span className="text-slate-400 text-xs shrink-0">
                  {formatTs(g.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      )}
    </main>
  );
}
