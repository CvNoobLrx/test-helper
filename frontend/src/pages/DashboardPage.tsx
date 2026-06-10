import { useMemo, useState, type ElementType } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Collection, GraphEdge, GraphNode, GraphResponse, KnowledgePoint, MasteryStats, ReviewItem } from "../api/types";
import { ArrowRight, BookOpen, FileText, GitBranch, MessageSquare, Sparkles, Target } from "lucide-react";
import { useAppStore } from "../stores/appStore";

export function DashboardPage() {
  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);
  const enableGraphRag = useAppStore((s) => s.enableGraphRag);
  const setGraphRagEnabled = useAppStore((s) => s.setGraphRagEnabled);
  const [graphType, setGraphType] = useState("all");
  const [graphImportantOnly, setGraphImportantOnly] = useState(false);
  const [selectedGraphNode, setSelectedGraphNode] = useState<string | null>(null);
  const encodedCollection = encodeURIComponent(collection || "default");

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<{ collections: Collection[] }>("/collections"),
  });

  const { data: docsData } = useQuery({
    queryKey: ["documents", collection],
    queryFn: () => api.get<{ documents: Array<{ source_path: string; chunk_count: number; processed_at?: string }> }>(`/documents?collection=${encodedCollection}`),
  });

  const { data: masteryData } = useQuery({
    queryKey: ["mastery", collection],
    queryFn: () => api.get<{ stats: MasteryStats }>(`/learning/mastery?collection=${encodedCollection}`),
  });

  const { data: reviewData } = useQuery({
    queryKey: ["review-plan", collection],
    queryFn: () => api.get<{ review_items: ReviewItem[] }>(`/learning/review-plan?collection=${encodedCollection}&max_items=4`),
  });

  const { data: kpsData } = useQuery({
    queryKey: ["knowledge-points", collection],
    queryFn: () => api.get<{ knowledge_points: KnowledgePoint[] }>(`/learning/knowledge-points?collection=${encodedCollection}`),
  });

  const { data: graphData } = useQuery({
    queryKey: ["graph", collection],
    queryFn: () => api.get<GraphResponse>(`/graph?collection=${encodedCollection}&limit=300`),
  });

  const collections = collectionsData?.collections || [];
  const documents = docsData?.documents || [];
  const mastery = masteryData?.stats;
  const reviewItems = reviewData?.review_items || [];
  const knowledgePoints = kpsData?.knowledge_points || [];
  const graph = graphData;
  const currentCollectionStats = collections.find((c) => c.name === collection);
  const graphStats = graph?.stats;
  const graphNodes = useMemo(() => {
    const nodes = graph?.nodes || [];
    return nodes.filter((node) => {
      if (graphType !== "all" && node.type !== graphType) return false;
      if (graphImportantOnly && (node.importance || 0) < 1.5) return false;
      return true;
    });
  }, [graph, graphImportantOnly, graphType]);
  const graphNodeIds = useMemo(() => new Set(graphNodes.map((node) => node.id)), [graphNodes]);
  const graphEdges = useMemo(
    () => (graph?.edges || []).filter((edge) => graphNodeIds.has(edge.source) && graphNodeIds.has(edge.target)),
    [graph, graphNodeIds]
  );
  const selectedNode = useMemo(
    () => graphNodes.find((node) => node.id === selectedGraphNode) || null,
    [graphNodes, selectedGraphNode]
  );
  const relatedNodeIds = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const related = new Set<string>([selectedNode.id]);
    graphEdges.forEach((edge) => {
      if (edge.source === selectedNode.id) related.add(edge.target);
      if (edge.target === selectedNode.id) related.add(edge.source);
    });
    return related;
  }, [graphEdges, selectedNode]);
  const graphSummary = useMemo(() => {
    const counts = graphNodes.reduce<Record<string, number>>((acc, node) => {
      acc[node.type] = (acc[node.type] || 0) + 1;
      return acc;
    }, {});
    return counts;
  }, [graphNodes]);

  const quickQuestions = [
    "这门课最重要的考试重点是什么？",
    "帮我总结这份资料的核心概念",
    "根据资料出 5 道选择题",
  ];

  return (
    <div className="p-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-950">今日复习</h1>
          <p className="mt-2 text-sm text-gray-500">围绕当前科目安排资料、问答和训练。</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          当前科目
          <select
            value={collection}
            onChange={(e) => setCollection(e.target.value || "default")}
            className="h-10 min-w-48 rounded-lg border bg-white px-3 text-sm text-gray-900"
          >
            {Array.from(new Set(["default", collection, ...collections.map((c) => c.name)].filter(Boolean))).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <StatCard icon={FileText} label="资料" value={documents.length} hint="已入库文件" />
        <StatCard icon={BookOpen} label="知识点" value={knowledgePoints.length} hint="可复习考点" />
        <StatCard icon={Target} label="待复习" value={reviewItems.length} hint="今天优先处理" />
        <StatCard icon={Sparkles} label="片段" value={currentCollectionStats?.chunk_count || currentCollectionStats?.total_chunks || 0} hint="可检索内容" />
      </div>

      <div className="mb-6 rounded-xl border bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <GitBranch size={18} className={enableGraphRag ? "text-blue-600" : "text-gray-400"} />
              <h2 className="text-lg font-semibold text-gray-950">知识图谱</h2>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              当前科目的知识结构、章节关系和资料来源。开启 Graph-RAG 后，问答会把这张图谱一起纳入检索。
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={enableGraphRag}
              onChange={(e) => setGraphRagEnabled(e.target.checked)}
            />
            Graph-RAG
          </label>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          {(["all", "knowledge_point", "chapter", "formula", "image", "document"] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setGraphType(type)}
              className={`rounded-full border px-3 py-1.5 ${
                graphType === type ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {type === "all" ? "全部" : type}
            </button>
          ))}
          <label className="ml-auto flex items-center gap-2 text-gray-600">
            <input type="checkbox" checked={graphImportantOnly} onChange={(e) => setGraphImportantOnly(e.target.checked)} />
            仅高频/重要
          </label>
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <GraphCanvas
            nodes={graphNodes}
            edges={graphEdges}
            selectedId={selectedGraphNode}
            highlightIds={relatedNodeIds}
            onNodeClick={(id) => setSelectedGraphNode((current) => (current === id ? null : id))}
          />
          <div className="rounded-lg border bg-gray-50 p-4">
            <div className="text-sm font-medium text-gray-900">图谱详情</div>
            {!graph ? (
              <div className="mt-3 text-sm text-gray-500">尚未加载图谱。</div>
            ) : !selectedNode ? (
              <div className="mt-3 space-y-2 text-sm text-gray-600">
                <div>节点 {graphStats?.visible_node_count ?? graphNodes.length}</div>
                <div>边 {graphStats?.visible_edge_count ?? graphEdges.length}</div>
                <div>孤立点 {graphStats?.isolated_count ?? 0}</div>
                {Object.entries(graphSummary).slice(0, 5).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between rounded bg-white px-3 py-2">
                    <span>{key}</span>
                    <span className="font-medium">{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 space-y-3 text-sm text-gray-600">
                <div>
                  <div className="text-xs text-gray-400">名称</div>
                  <div className="font-medium text-gray-900">{selectedNode.label}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">类型</div>
                  <div>{selectedNode.type}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">来源</div>
                  <div className="break-all">{String(selectedNode.doc_hash || selectedNode.metadata?.doc_hash || "未知")}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">关联片段</div>
                  <div>{selectedNode.chunk_ids?.length || 0}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">元数据</div>
                  <pre className="max-h-40 overflow-auto rounded bg-white p-2 text-xs text-gray-500">
                    {JSON.stringify(selectedNode.metadata || {}, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-950">今天先做什么</h2>
            <Link to="/learning" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
              进入训练 <ArrowRight size={14} />
            </Link>
          </div>
          {reviewItems.length === 0 ? (
            <div className="rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
              暂时没有待复习项目。可以先上传资料，或在知识问答里让助手总结考试重点。
            </div>
          ) : (
            <div className="space-y-3">
              {reviewItems.map((item) => (
                <div key={item.knowledge_point_id} className="rounded-lg bg-gray-50 p-4">
                  <div className="text-sm font-medium text-gray-900">{item.content}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    {item.category || "知识点"} · 间隔 {item.interval_days || 1} 天
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-950">快速提问</h2>
            <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
              打开问答 <ArrowRight size={14} />
            </Link>
          </div>
          <div className="space-y-3">
            {quickQuestions.map((question) => (
              <Link
                key={question}
                to={`/chat?q=${encodeURIComponent(question)}`}
                className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm text-gray-700 hover:border-blue-200 hover:bg-blue-50"
              >
                <span>{question}</span>
                <MessageSquare size={16} className="text-gray-400" />
              </Link>
            ))}
          </div>
          <div className="mt-4 rounded-lg bg-blue-50 p-4 text-sm text-blue-800">
            当前会基于“{collection || "default"}”资料库回答。没有资料依据时，助手会明确说明找不到依据。
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-950">最近资料</h2>
            <Link to="/documents" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
              管理资料 <ArrowRight size={14} />
            </Link>
          </div>
          {documents.length === 0 ? (
            <p className="text-sm text-gray-500">当前科目还没有资料。上传课件、教材或笔记后开始复习。</p>
          ) : (
            <div className="space-y-2">
              {documents.slice(0, 4).map((doc) => (
                <div key={doc.source_path} className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3">
                  <span className="min-w-0 truncate text-sm font-medium text-gray-900">
                    {doc.source_path.split(/[/\\]/).pop()}
                  </span>
                  <span className="ml-3 shrink-0 text-xs text-gray-500">{doc.chunk_count || 0} 片段</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-950">掌握情况</h2>
          <div className="grid grid-cols-3 gap-3">
            <MiniStat label="已掌握" value={mastery?.mastered || 0} tone="green" />
            <MiniStat label="学习中" value={mastery?.learning || 0} tone="yellow" />
            <MiniStat label="需复习" value={mastery?.needs_review || 0} tone="red" />
          </div>
          <p className="mt-4 text-sm text-gray-500">
            这些数据来自复习训练中的掌握度记录，用来决定下一次复习顺序。
          </p>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, hint }: { icon: ElementType; label: string; value: number; hint: string }) {
  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="flex items-center gap-3 mb-2">
        <Icon size={20} className="text-blue-500" />
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      <div className="mt-1 text-xs text-gray-400">{hint}</div>
    </div>
  );
}

function GraphCanvas({
  nodes,
  edges,
  selectedId,
  highlightIds,
  onNodeClick,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  highlightIds: Set<string>;
  onNodeClick: (id: string) => void;
}) {
  const width = 860;
  const height = 420;
  const positions = useMemo(() => layoutGraph(nodes, edges, width, height), [nodes, edges]);

  if (nodes.length === 0) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-lg border bg-gray-50 text-sm text-gray-500">
        当前筛选下没有可展示的图谱节点。
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-slate-950">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[420px] w-full">
        <rect width={width} height={height} fill="#020617" />
        {edges.map((edge) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const highlighted = !selectedId || highlightIds.has(edge.source) || highlightIds.has(edge.target);
          return (
            <line
              key={edge.id}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={highlighted ? "#60a5fa" : "#334155"}
              strokeOpacity={highlighted ? 0.55 : 0.22}
              strokeWidth={Math.max(1, Math.min(3, edge.weight || 1))}
            />
          );
        })}
        {nodes.map((node) => {
          const point = positions.get(node.id);
          if (!point) return null;
          const isSelected = node.id === selectedId;
          const isDimmed = selectedId ? !highlightIds.has(node.id) : false;
          const radius = node.type === "document" ? 14 : node.type === "chapter" ? 11 : Math.max(7, Math.min(13, 7 + (node.importance || 1)));
          return (
            <g
              key={node.id}
              transform={`translate(${point.x}, ${point.y})`}
              className="cursor-pointer"
              onClick={() => onNodeClick(node.id)}
            >
              <circle
                r={radius + (isSelected ? 5 : 0)}
                fill={isSelected ? "#dbeafe" : colorForNode(node.type)}
                opacity={isDimmed ? 0.28 : 0.95}
                stroke={isSelected ? "#ffffff" : "#0f172a"}
                strokeWidth={isSelected ? 3 : 1.5}
              />
              <text
                x={radius + 6}
                y={4}
                fill={isDimmed ? "#64748b" : "#e5e7eb"}
                fontSize={node.type === "document" ? 13 : 11}
                style={{ pointerEvents: "none" }}
              >
                {shortLabel(node.label)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function layoutGraph(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number) {
  const positions = new Map<string, { x: number; y: number }>();
  if (nodes.length === 0) return positions;

  const centerX = width / 2;
  const centerY = height / 2;
  const byType = nodes.reduce<Record<string, GraphNode[]>>((acc, node) => {
    acc[node.type] = acc[node.type] || [];
    acc[node.type].push(node);
    return acc;
  }, {});
  const typeOrder = ["document", "chapter", "knowledge_point", "formula", "image", "question", "concept"];
  const orderedTypes = [...typeOrder.filter((type) => byType[type]), ...Object.keys(byType).filter((type) => !typeOrder.includes(type))];
  const maxRadius = Math.min(width, height) * 0.42;

  orderedTypes.forEach((type, typeIndex) => {
    const group = byType[type];
    const radius = orderedTypes.length === 1 ? maxRadius * 0.55 : 35 + (maxRadius - 35) * (typeIndex / Math.max(1, orderedTypes.length - 1));
    group.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, group.length) + typeIndex * 0.47;
      positions.set(node.id, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      });
    });
  });

  for (let tick = 0; tick < 90; tick += 1) {
    edges.forEach((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const desired = 90;
      const force = (distance - desired) * 0.006;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      source.x += fx;
      source.y += fy;
      target.x -= fx;
      target.y -= fy;
    });
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = positions.get(nodes[i].id);
        const b = positions.get(nodes[j].id);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        if (distance > 58) continue;
        const force = (58 - distance) * 0.012;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.x -= fx;
        a.y -= fy;
        b.x += fx;
        b.y += fy;
      }
    }
  }

  positions.forEach((point) => {
    point.x = Math.max(24, Math.min(width - 130, point.x));
    point.y = Math.max(24, Math.min(height - 24, point.y));
  });
  return positions;
}

function colorForNode(type: string) {
  const colors: Record<string, string> = {
    document: "#f97316",
    chapter: "#22c55e",
    knowledge_point: "#38bdf8",
    formula: "#a78bfa",
    image: "#facc15",
    question: "#fb7185",
    concept: "#14b8a6",
  };
  return colors[type] || "#94a3b8";
}

function shortLabel(label: string) {
  const compact = label.replace(/\s+/g, " ").trim();
  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact;
}

function MiniStat({ label, value, tone }: { label: string; value: number; tone: "green" | "yellow" | "red" }) {
  const classes = {
    green: "bg-green-50 text-green-700 border-green-100",
    yellow: "bg-yellow-50 text-yellow-700 border-yellow-100",
    red: "bg-red-50 text-red-700 border-red-100",
  };
  return (
    <div className={`rounded-lg border p-4 ${classes[tone]}`}>
      <div className="text-xs">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </div>
  );
}
