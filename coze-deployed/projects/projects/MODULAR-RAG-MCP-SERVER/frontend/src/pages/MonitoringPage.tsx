import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Trace, ComponentInfo } from "../api/types";
import { Activity, CheckCircle2, RefreshCw, Settings } from "lucide-react";

type Tab = "traces" | "config";

export function MonitoringPage() {
  const [tab, setTab] = useState<Tab>("traces");

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">系统状态</h1>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {([
          ["traces", "运行记录", Activity],
          ["config", "组件配置", Settings],
        ] as [Tab, string, React.ElementType][]).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === key ? "bg-white shadow text-gray-900" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {tab === "traces" && <TracesTab />}
      {tab === "config" && <ConfigTab />}
    </div>
  );
}

function TracesTab() {
  const [filter, setFilter] = useState<string>("ingestion");
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["traces", filter],
    queryFn: () =>
      api.get<{ traces: Trace[] }>(
        `/monitoring/traces?limit=50${filter ? `&trace_type=${filter}` : ""}`
      ),
  });

  const traces = data?.traces || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-2">
        {[
          ["ingestion", "资料处理"],
          ["query", "问答检索"],
          ["", "全部"],
        ].map(([t, label]) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-lg text-sm ${
              filter === t ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
            }`}
          >
            {label}
          </button>
        ))}
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          {isFetching ? "刷新中" : "刷新"}
        </button>
      </div>

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error instanceof Error ? error.message : "运行记录读取失败"}
        </div>
      )}

      <div className="bg-white rounded-xl border">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">正在读取运行记录...</div>
        ) : traces.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无记录。上传资料或进行问答后再刷新。</div>
        ) : (
          <div className="divide-y max-h-[600px] overflow-auto">
            {traces.map((trace) => (
              <TraceRow key={trace.trace_id} trace={trace} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TraceRow({ trace }: { trace: Trace }) {
  const [expanded, setExpanded] = useState(false);
  const stageCount = trace.stages?.length || 0;
  const totalTime =
    trace.total_elapsed_ms ||
    trace.stages?.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0) ||
    0;
  const isIngestion = trace.trace_type === "ingestion";
  const title = getTraceTitle(trace);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 hover:bg-gray-50 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <span
            className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              trace.trace_type === "query"
                ? "bg-blue-100 text-blue-700"
                : "bg-purple-100 text-purple-700"
            }`}
          >
            {trace.trace_type === "query" ? "问答" : "资料处理"}
          </span>
          <span className="text-sm text-gray-900">{title}</span>
          {isIngestion && trace.raw_stage_count && trace.raw_stage_count > stageCount && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
              已汇总 {trace.raw_stage_count} 条内部事件
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>{stageCount} 个阶段</span>
          <span>{formatDuration(totalTime)}</span>
          <span>{formatTime(trace.started_at)}</span>
        </div>
      </button>

      {expanded && trace.stages && (
        <div className="px-4 pb-3">
          <div className="bg-gray-50 rounded-lg p-3 space-y-2">
            {trace.stages.map((stage, i) => (
              <div key={`${stage.stage}-${i}`} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <div className="flex min-w-0 items-center gap-2">
                    <CheckCircle2 size={15} className="shrink-0 text-emerald-500" />
                    <span className="font-medium text-gray-800">{stage.label || stage.stage}</span>
                    {stage.summary && <span className="truncate text-gray-500">{stage.summary}</span>}
                  </div>
                  <span className="shrink-0 text-gray-500">{formatDuration(stage.elapsed_ms || 0)}</span>
                </div>
                {totalTime > 0 && stage.elapsed_ms > 0 && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100" title="该阶段在总耗时中的占比">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full"
                      style={{
                        width: `${Math.max(4, Math.min(100, (stage.elapsed_ms / totalTime) * 100))}%`,
                      }}
                    />
                  </div>
                )}
                {isIngestion && stage.data && Object.keys(stage.data).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(stage.data)
                      .filter(([, value]) => value !== "" && value !== 0 && value !== null && value !== undefined)
                      .slice(0, 5)
                      .map(([key, value]) => (
                        <span key={key} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                          {labelDataKey(key)}: {String(value)}
                        </span>
                      ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function getTraceTitle(trace: Trace) {
  const metadata = trace.metadata || {};
  const raw = String(metadata.query || metadata.file_name || metadata.file_path || trace.trace_id?.slice(0, 8) || "");
  return raw.split("\\").pop()?.split("/").pop() || raw;
}

function formatDuration(ms: number) {
  if (ms < 0) return "无耗时记录";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function formatTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(11, 19);
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function labelDataKey(key: string) {
  const labels: Record<string, string> = {
    doc_id: "文档",
    text_length: "字数",
    image_count: "图片",
    chunk_count: "片段",
    avg_chunk_size: "平均长度",
    refined_by_llm: "LLM整理",
    refined_by_rule: "规则整理",
    enriched_by_llm: "LLM摘要",
    enriched_by_rule: "规则摘要",
    captioned_chunks: "图片说明",
    dense_vector_count: "向量",
    dense_dimension: "维度",
    failed_chunks: "失败片段",
    vector_count: "写入片段",
    collection: "资料库",
  };
  return labels[key] || key;
}

function ConfigTab() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["config"],
    queryFn: () => api.get<{ components: ComponentInfo[] }>("/monitoring/config"),
  });

  const components = data?.components || [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => refetch()}
          className="rounded-lg border bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          {isFetching ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error instanceof Error ? error.message : "Failed to load config"}
        </div>
      )}
      {isLoading && <div className="rounded-xl border bg-white p-8 text-center text-gray-500">Loading config...</div>}
      {!isLoading && components.length === 0 && (
        <div className="rounded-xl border bg-white p-8 text-center text-gray-500">No component config returned.</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {components.map((c) => (
        <div key={c.name} className="bg-white rounded-xl border p-5">
          <div className="flex items-center gap-2 mb-3">
            <Settings size={16} className="text-gray-400" />
            <h3 className="font-semibold text-gray-900">{c.name}</h3>
          </div>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Provider</span>
              <span className="font-medium">{c.provider}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Model</span>
              <span className="font-medium">{c.model}</span>
            </div>
            {Object.entries(c.extra).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-gray-500">{k}</span>
                <span className="font-medium">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
        ))}
      </div>
    </div>
  );
}
