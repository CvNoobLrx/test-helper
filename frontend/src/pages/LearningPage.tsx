import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { KnowledgePoint, MasteryStats, QuizQuestion, ReviewItem } from "../api/types";
import { BookOpen, Brain, ChevronDown, HelpCircle } from "lucide-react";
import { useAppStore } from "../stores/appStore";

type Tab = "overview" | "review" | "quiz";

export function LearningPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-950">复习训练</h1>
          <p className="mt-2 text-sm text-gray-500">查看知识点、安排今日复习，并从资料中生成测验。</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          当前科目
          <input
            value={collection}
            onChange={(e) => setCollection(e.target.value || "default")}
            className="w-44 rounded-lg border px-3 py-2 text-sm text-gray-800"
          />
        </label>
      </div>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {([
          ["overview", "知识点", BookOpen],
          ["review", "今日复习", Brain],
          ["quiz", "生成测验", HelpCircle],
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

      {tab === "overview" && <OverviewTab collection={collection} onStartReview={() => setTab("review")} />}
      {tab === "review" && <ReviewTab collection={collection} />}
      {tab === "quiz" && <QuizTab collection={collection} />}
    </div>
  );
}

function OverviewTab({ collection, onStartReview }: { collection: string; onStartReview: () => void }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const encodedCollection = encodeURIComponent(collection || "default");
  const { data: statsData } = useQuery({
    queryKey: ["mastery", collection],
    queryFn: () => api.get<{ stats: MasteryStats }>(`/learning/mastery?collection=${encodedCollection}`),
  });

  const { data: kpsData } = useQuery({
    queryKey: ["knowledge-points", collection],
    queryFn: () => api.get<{ knowledge_points: KnowledgePoint[] }>(`/learning/knowledge-points?collection=${encodedCollection}`),
  });

  const stats = statsData?.stats;
  const kps = kpsData?.knowledge_points || [];
  const selected = kps.find((kp) => kp.id === expandedId);
  const groupedKps = kps.reduce<Record<string, KnowledgePoint[]>>((acc, kp) => {
    const topic = kp.topic || "综合考点";
    acc[topic] = acc[topic] || [];
    acc[topic].push(kp);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border p-5">
            <div className="text-sm text-gray-500 mb-1">全部知识点</div>
            <div className="text-2xl font-bold">{stats.total}</div>
          </div>
          <div className="bg-green-50 rounded-xl border border-green-200 p-5" title="至少复习 2 次、正确率较高且复习间隔已拉开的知识点">
            <div className="text-sm text-green-600 mb-1">已掌握</div>
            <div className="text-2xl font-bold text-green-700">{stats.mastered}</div>
          </div>
          <div className="bg-yellow-50 rounded-xl border border-yellow-200 p-5" title="已经复习过，但还没有达到稳定掌握标准的知识点">
            <div className="text-sm text-yellow-600 mb-1">学习中</div>
            <div className="text-2xl font-bold text-yellow-700">{stats.learning}</div>
          </div>
          <div className="bg-red-50 rounded-xl border border-red-200 p-5" title="还没复习过，或近期回忆效果较差的知识点">
            <div className="text-sm text-red-600 mb-1">需复习</div>
            <div className="text-2xl font-bold text-red-700">{stats.needs_review}</div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">知识点总览 ({kps.length})</h2>
          <span className="text-xs text-gray-500">点击知识点查看来源、重要度和复习建议</span>
        </div>
        {kps.length === 0 ? (
          <p className="text-gray-500 text-sm">还没有提取到知识点。上传资料并完成解析后会出现在这里。</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
          <div className="max-h-96 overflow-auto space-y-4">
            {Object.entries(groupedKps).map(([topic, items]) => (
              <section key={topic}>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-900">{topic}</h3>
                  <span className="text-xs text-gray-400">{items.length} 个考点</span>
                </div>
                <div className="space-y-2">
                  {items.map((kp) => (
                    <button
                      key={kp.id}
                      onClick={() => setExpandedId((id) => (id === kp.id ? null : kp.id))}
                      className={`w-full rounded-lg p-3 text-left ${
                        expandedId === kp.id ? "bg-blue-50 ring-1 ring-blue-200" : "bg-gray-50 hover:bg-gray-100"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-xs text-gray-500 mb-1">{kp.subtopic || kp.category || "考点"}</div>
                          <div className="text-sm font-medium text-gray-900">{kp.content || kp.text}</div>
                        </div>
                        <ChevronDown size={16} className="mt-0.5 shrink-0 text-gray-400" />
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {kp.category || "知识点"} · 重要度 {kp.importance ?? 3}
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="rounded-lg border bg-gray-50 p-4">
            {selected ? (
              <div>
                <div className="text-xs text-gray-500 mb-2">知识点详情</div>
                <div className="text-sm font-medium text-gray-900 leading-6">{selected.content || selected.text}</div>
                <div className="mt-3 space-y-1 text-xs text-gray-500">
                  <div>主题：{selected.topic || "综合考点"}</div>
                  <div>考点：{selected.subtopic || selected.category || "知识点"}</div>
                  <div>类型：{selected.category || "知识点"}</div>
                  <div>重要度：{selected.importance ?? 3}</div>
                  {selected.exam_focus && <div>复习建议：{selected.exam_focus}</div>}
                  {selected.source_ref && <div className="break-all">来源：{selected.source_ref}</div>}
                  {selected.chunk_id && <div className="break-all">片段：{selected.chunk_id}</div>}
                </div>
                <button
                  onClick={onStartReview}
                  className="mt-4 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  去今日复习
                </button>
              </div>
            ) : (
              <p className="text-sm text-gray-500">选择左侧知识点查看来源、重要度和考试复习建议。</p>
            )}
          </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewTab({ collection }: { collection: string }) {
  const encodedCollection = encodeURIComponent(collection || "default");
  const { data, refetch } = useQuery({
    queryKey: ["review-plan", collection],
    queryFn: () => api.get<{ review_items: ReviewItem[] }>(`/learning/review-plan?collection=${encodedCollection}&max_items=5`),
  });

  const [currentIndex, setCurrentIndex] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const submitMutation = useMutation({
    mutationFn: (quality: number) =>
      api.post("/learning/review/submit", {
        collection,
        knowledge_point_id: items[currentIndex]?.knowledge_point_id,
        quality,
      }),
    onSuccess: () => setSubmitted(true),
  });

  const items = data?.review_items || [];
  const current = items[currentIndex];

  if (items.length === 0) {
    return (
      <div className="bg-white rounded-xl border p-8 text-center">
        <Brain size={48} className="mx-auto text-gray-300 mb-4" />
        <p className="text-gray-500">今天暂时没有待复习项目。</p>
        <button onClick={() => refetch()} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">
          刷新
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="rounded-xl border bg-white p-6">
        <div className="mb-4 flex items-center justify-between text-sm text-gray-500">
          <span>复习卡片 {currentIndex + 1} / {items.length}</span>
          <span>{current?.category || "知识点"}</span>
        </div>

        <div className="rounded-lg bg-gray-50 p-5">
          <div className="text-xs font-medium text-gray-500">先遮住资料，凭记忆解释这个知识点</div>
          <div className="mt-3 text-lg font-semibold leading-8 text-gray-950">{current?.content || "正在加载..."}</div>
          <div className="mt-3 text-xs text-gray-500">复习间隔：{current?.interval_days || 1} 天</div>
        </div>

        {!revealed ? (
          <div className="mt-5">
            <button
              onClick={() => setRevealed(true)}
              className="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-800"
            >
              我想好了，记录掌握度
            </button>
          </div>
        ) : !submitted ? (
          <div>
            <p className="mb-3 mt-5 text-sm text-gray-600">这次回忆得怎么样？0 表示完全不会，5 表示很熟。</p>
            <div className="flex gap-2">
              {[0, 1, 2, 3, 4, 5].map((q) => (
                <button
                  key={q}
                  onClick={() => submitMutation.mutate(q)}
                  className="w-10 h-10 rounded-lg border text-sm font-medium hover:bg-blue-50 hover:border-blue-300"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div>
            <p className="text-green-600 text-sm mb-3">已记录掌握度，并安排下次复习。</p>
            <button
              onClick={() => {
                setSubmitted(false);
                setRevealed(false);
                setCurrentIndex(0);
                refetch();
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
            >
              下一项
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function QuizTab({ collection }: { collection: string }) {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);
  const [score, setScore] = useState(0);
  const [quizError, setQuizError] = useState("");

  const generateMutation = useMutation({
    mutationFn: () =>
      api.post<{ questions: QuizQuestion[]; error?: string }>("/learning/quiz/generate", {
        collection,
        num_questions: 5,
        difficulty: "medium",
      }),
    onSuccess: (data) => {
      setQuestions(data.questions || []);
      setQuizError(data.error || "");
      setCurrentIdx(0);
      setScore(0);
      setSelected(null);
      setShowAnswer(false);
    },
  });

  const current = questions[currentIdx];
  const questionTypeLabel = {
    mcq: "选择题",
    true_false: "判断题",
    short_answer: "简答题",
  }[current?.type || "mcq"];
  const normalizeAnswer = (value: string | null | undefined) => {
    const text = String(value || "").trim().toLowerCase();
    if (["true", "正确", "对", "是"].includes(text)) return "true";
    if (["false", "错误", "错", "否"].includes(text)) return "false";
    return text;
  };
  const displayAnswer = (value: string) => {
    const normalized = normalizeAnswer(value);
    if (normalized === "true") return "正确";
    if (normalized === "false") return "错误";
    return value;
  };

  return (
    <div className="max-w-xl">
      {questions.length === 0 ? (
        <div className="bg-white rounded-xl border p-8 text-center">
          <HelpCircle size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 mb-4">根据当前科目的知识点生成一组练习题。</p>
          <button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {generateMutation.isPending ? "正在生成..." : "生成测验"}
          </button>
          {generateMutation.isError && (
            <p className="text-red-500 text-sm mt-2">测验生成失败，请稍后重试。</p>
          )}
          {quizError && (
            <p className="text-red-500 text-sm mt-2">{quizError}</p>
          )}
        </div>
      ) : currentIdx >= questions.length ? (
        <div className="bg-white rounded-xl border p-8 text-center">
          <p className="text-2xl font-bold mb-2">测验完成</p>
          <p className="text-gray-600">得分：{score} / {questions.length}</p>
          <button
            onClick={() => generateMutation.mutate()}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
          >
            再来一组
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border p-6">
          <div className="text-sm text-gray-500 mb-2">
            第 {currentIdx + 1} 题 / 共 {questions.length} 题 · {questionTypeLabel}
          </div>
          <div className="text-lg mb-6">{current.question}</div>

          {current.type === "mcq" && current.options && (
            <div className="space-y-2 mb-4">
              {current.options.map((opt) => (
                <button
                  key={opt}
                  onClick={() => { setSelected(opt); setShowAnswer(true); }}
                  className={`w-full text-left px-4 py-3 rounded-lg border text-sm ${
                    showAnswer
                      ? opt === current.correct_answer
                        ? "bg-green-50 border-green-300 text-green-800"
                        : opt === selected
                        ? "bg-red-50 border-red-300 text-red-800"
                        : "bg-gray-50"
                      : "hover:bg-gray-50"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {current.type === "true_false" && (
            <div className="flex gap-2 mb-4">
              {[
                ["True", "正确"],
                ["False", "错误"],
              ].map(([opt, label]) => (
                <button
                  key={opt}
                  onClick={() => { setSelected(opt); setShowAnswer(true); }}
                  className={`px-6 py-3 rounded-lg border text-sm ${
                    showAnswer
                      ? opt === current.correct_answer
                        ? "bg-green-50 border-green-300"
                        : opt === selected
                        ? "bg-red-50 border-red-300"
                        : "bg-gray-50"
                      : "hover:bg-gray-50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {current.type === "short_answer" && !showAnswer && (
            <div className="mb-4">
              <input
                type="text"
                value={selected || ""}
                onChange={(e) => setSelected(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && setShowAnswer(true)}
                placeholder="输入你的答案..."
                className="w-full px-4 py-2 border rounded-lg text-sm"
              />
              <button
                onClick={() => setShowAnswer(true)}
                className="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
              >
                提交
              </button>
            </div>
          )}

          {showAnswer && (
            <div className="mt-4 p-4 bg-blue-50 rounded-lg">
              <div className="text-sm font-medium text-blue-900 mb-1">
                参考答案：{displayAnswer(current.correct_answer)}
              </div>
              <div className="text-sm text-blue-700">{current.explanation}</div>
              <button
                onClick={() => {
                  if (normalizeAnswer(selected) === normalizeAnswer(current.correct_answer)) setScore((s) => s + 1);
                  setCurrentIdx((i) => i + 1);
                  setSelected(null);
                  setShowAnswer(false);
                }}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
              >
                下一题
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
