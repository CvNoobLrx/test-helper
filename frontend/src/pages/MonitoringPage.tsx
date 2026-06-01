import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Trace, ComponentInfo } from "../api/types";
import { Activity, Settings } from "lucide-react";

type Tab = "traces" | "config";

export function MonitoringPage() {
  const [tab, setTab] = useState<Tab>("traces");

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Monitoring</h1>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {([
          ["traces", "Traces", Activity],
          ["config", "Config", Settings],
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
  const [filter, setFilter] = useState<string>("");
  const { data } = useQuery({
    queryKey: ["traces", filter],
    queryFn: () =>
      api.get<{ traces: Trace[] }>(
        `/monitoring/traces?limit=50${filter ? `&trace_type=${filter}` : ""}`
      ),
  });

  const traces = data?.traces || [];

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {["", "query", "ingestion"].map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-lg text-sm ${
              filter === t ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
            }`}
          >
            {t || "All"}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border">
        {traces.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No traces found</div>
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
  const totalTime = trace.stages?.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0) || 0;

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
            {trace.trace_type}
          </span>
          <span className="text-sm text-gray-900">
            {String(trace.metadata?.query || trace.metadata?.file_path || trace.trace_id?.slice(0, 8) || "")}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>{stageCount} stages</span>
          <span>{totalTime.toFixed(0)}ms</span>
          <span>{trace.started_at?.slice(11, 19)}</span>
        </div>
      </button>

      {expanded && trace.stages && (
        <div className="px-4 pb-3">
          <div className="bg-gray-50 rounded-lg p-3 space-y-2">
            {trace.stages.map((stage, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-700">{stage.stage}</span>
                <div className="flex items-center gap-4">
                  <div className="w-32 bg-gray-200 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full"
                      style={{
                        width: `${Math.min(100, (stage.elapsed_ms / totalTime) * 100)}%`,
                      }}
                    />
                  </div>
                  <span className="text-gray-500 w-16 text-right">{stage.elapsed_ms?.toFixed(0)}ms</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfigTab() {
  const { data } = useQuery({
    queryKey: ["config"],
    queryFn: () => api.get<{ components: ComponentInfo[] }>("/monitoring/config"),
  });

  const components = data?.components || [];

  return (
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
  );
}
