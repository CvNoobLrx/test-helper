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
        <h1 className="text-2xl font-bold text-gray-900">复习计划</h1>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          资料库
          <input
            value={collection}
            onChange={(e) => setCollection(e.target.value || "default")}
            className="w-44 rounded-lg border px-3 py-2 text-sm text-gray-800"
          />
        </label>
      </div>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {([
          ["overview", "Overview", BookOpen],
          ["review", "Review", Brain],
          ["quiz", "Quiz", HelpCircle],
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
  const { data: statsData } = useQuery({
    queryKey: ["mastery", collection],
    queryFn: () => api.get<{ stats: MasteryStats }>(`/learning/mastery?collection=${collection}`),
  });

  const { data: kpsData } = useQuery({
    queryKey: ["knowledge-points", collection],
    queryFn: () => api.get<{ knowledge_points: KnowledgePoint[] }>(`/learning/knowledge-points?collection=${collection}`),
  });

  const stats = statsData?.stats;
  const kps = kpsData?.knowledge_points || [];
  const selected = kps.find((kp) => kp.id === expandedId);

  return (
    <div className="space-y-6">
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border p-5">
            <div className="text-sm text-gray-500 mb-1">Total</div>
            <div className="text-2xl font-bold">{stats.total}</div>
          </div>
          <div className="bg-green-50 rounded-xl border border-green-200 p-5">
            <div className="text-sm text-green-600 mb-1">Mastered</div>
            <div className="text-2xl font-bold text-green-700">{stats.mastered}</div>
          </div>
          <div className="bg-yellow-50 rounded-xl border border-yellow-200 p-5">
            <div className="text-sm text-yellow-600 mb-1">Learning</div>
            <div className="text-2xl font-bold text-yellow-700">{stats.learning}</div>
          </div>
          <div className="bg-red-50 rounded-xl border border-red-200 p-5">
            <div className="text-sm text-red-600 mb-1">Needs Review</div>
            <div className="text-2xl font-bold text-red-700">{stats.needs_review}</div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">知识点清单 ({kps.length})</h2>
          <span className="text-xs text-gray-500">点击知识点查看详情，或加入复习</span>
        </div>
        {kps.length === 0 ? (
          <p className="text-gray-500 text-sm">No knowledge points extracted yet.</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
          <div className="space-y-2 max-h-96 overflow-auto">
            {kps.map((kp) => (
              <button
                key={kp.id}
                onClick={() => setExpandedId((id) => (id === kp.id ? null : kp.id))}
                className={`w-full rounded-lg p-3 text-left ${
                  expandedId === kp.id ? "bg-blue-50 ring-1 ring-blue-200" : "bg-gray-50 hover:bg-gray-100"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-medium text-gray-900">{kp.content || kp.text}</div>
                  <ChevronDown size={16} className="mt-0.5 shrink-0 text-gray-400" />
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {kp.category || "知识点"} · 重要度 {kp.importance ?? 3}
                </div>
              </button>
            ))}
          </div>
          <div className="rounded-lg border bg-gray-50 p-4">
            {selected ? (
              <div>
                <div className="text-xs text-gray-500 mb-2">知识点详情</div>
                <div className="text-sm font-medium text-gray-900 leading-6">{selected.content || selected.text}</div>
                <div className="mt-3 space-y-1 text-xs text-gray-500">
                  <div>类型：{selected.category || "知识点"}</div>
                  <div>重要度：{selected.importance ?? 3}</div>
                  {selected.source_ref && <div className="break-all">来源：{selected.source_ref}</div>}
                  {selected.chunk_id && <div className="break-all">片段：{selected.chunk_id}</div>}
                </div>
                <button
                  onClick={onStartReview}
                  className="mt-4 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  去 Review 复习
                </button>
              </div>
            ) : (
              <p className="text-sm text-gray-500">选择左侧知识点查看来源、重要度，并把它加入复习队列。</p>
            )}
          </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewTab({ collection }: { collection: string }) {
  const { data, refetch } = useQuery({
    queryKey: ["review-plan", collection],
    queryFn: () => api.get<{ review_items: ReviewItem[] }>(`/learning/review-plan?collection=${collection}&max_items=5`),
  });

  const [currentIndex, setCurrentIndex] = useState(0);
  const [submitted, setSubmitted] = useState(false);

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
        <p className="text-gray-500">No items due for review. Great job!</p>
        <button onClick={() => refetch()} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">
          Refresh
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      <div className="bg-white rounded-xl border p-6">
        <div className="text-sm text-gray-500 mb-2">
          {currentIndex + 1} / {items.length}
        </div>
        <div className="text-lg mb-2">{current?.content || "Loading..."}</div>
        <div className="text-xs text-gray-500 mb-6">
          {current?.category || "知识点"} · 间隔 {current?.interval_days || 1} 天
        </div>

        {!submitted ? (
          <div>
            <p className="text-sm text-gray-600 mb-3">How well did you recall this?</p>
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
            <p className="text-green-600 text-sm mb-3">Recorded! Next review scheduled.</p>
            <button
              onClick={() => {
                setCurrentIndex((i) => i + 1);
                setSubmitted(false);
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
            >
              Next
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

  const generateMutation = useMutation({
    mutationFn: () =>
      api.post<{ questions: QuizQuestion[] }>("/learning/quiz/generate", {
        collection,
        num_questions: 5,
        difficulty: "medium",
      }),
    onSuccess: (data) => {
      setQuestions(data.questions || []);
      setCurrentIdx(0);
      setScore(0);
      setSelected(null);
      setShowAnswer(false);
    },
  });

  const current = questions[currentIdx];

  return (
    <div className="max-w-xl">
      {questions.length === 0 ? (
        <div className="bg-white rounded-xl border p-8 text-center">
          <HelpCircle size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 mb-4">Generate a quiz from your knowledge points</p>
          <button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {generateMutation.isPending ? "Generating..." : "Generate Quiz"}
          </button>
          {generateMutation.isError && (
            <p className="text-red-500 text-sm mt-2">Failed to generate quiz</p>
          )}
        </div>
      ) : currentIdx >= questions.length ? (
        <div className="bg-white rounded-xl border p-8 text-center">
          <p className="text-2xl font-bold mb-2">Quiz Complete!</p>
          <p className="text-gray-600">Score: {score} / {questions.length}</p>
          <button
            onClick={() => generateMutation.mutate()}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
          >
            New Quiz
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border p-6">
          <div className="text-sm text-gray-500 mb-2">
            Question {currentIdx + 1} / {questions.length} · {current.type}
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
              {["True", "False"].map((opt) => (
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
                  {opt}
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
                placeholder="Your answer..."
                className="w-full px-4 py-2 border rounded-lg text-sm"
              />
              <button
                onClick={() => setShowAnswer(true)}
                className="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
              >
                Submit
              </button>
            </div>
          )}

          {showAnswer && (
            <div className="mt-4 p-4 bg-blue-50 rounded-lg">
              <div className="text-sm font-medium text-blue-900 mb-1">
                Answer: {current.correct_answer}
              </div>
              <div className="text-sm text-blue-700">{current.explanation}</div>
              <button
                onClick={() => {
                  if (selected === current.correct_answer) setScore((s) => s + 1);
                  setCurrentIdx((i) => i + 1);
                  setSelected(null);
                  setShowAnswer(false);
                }}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
