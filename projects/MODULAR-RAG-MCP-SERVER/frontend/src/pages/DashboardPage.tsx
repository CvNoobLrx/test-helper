import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Collection, KnowledgePoint, MasteryStats, ReviewItem } from "../api/types";
import { ArrowRight, BookOpen, FileText, MessageSquare, Sparkles, Target } from "lucide-react";
import { useAppStore } from "../stores/appStore";

export function DashboardPage() {
  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);
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

  const collections = collectionsData?.collections || [];
  const documents = docsData?.documents || [];
  const mastery = masteryData?.stats;
  const reviewItems = reviewData?.review_items || [];
  const knowledgePoints = kpsData?.knowledge_points || [];
  const currentCollectionStats = collections.find((c) => c.name === collection);

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

function StatCard({ icon: Icon, label, value, hint }: { icon: React.ElementType; label: string; value: number; hint: string }) {
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
