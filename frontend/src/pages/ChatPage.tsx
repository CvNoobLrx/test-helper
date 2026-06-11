import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, GitBranch, HelpCircle, MessageSquarePlus, Send, Trash2, UserRound } from "lucide-react";
import { api, streamQuery } from "../api/client";
import type { Citation, Collection } from "../api/types";
import { useAppStore } from "../stores/appStore";
import { useChatStore } from "../stores/chatStore";
import { createId } from "../utils/id";

function extractCitedIndexes(content: string) {
  const indexes = new Set<number>();
  for (const match of content.matchAll(/\[([\d,\s，、]+)\]/g)) {
    const raw = match[1] || "";
    raw
      .split(/[,，、\s]+/)
      .map((part) => Number(part.trim()))
      .filter((value) => Number.isInteger(value) && value > 0)
      .forEach((value) => indexes.add(value));
  }
  return indexes;
}

export function ChatPage() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [collectionDraft, setCollectionDraft] = useState("");
  const [enableRerank, setEnableRerank] = useState(false);
  const [hoveredCitationId, setHoveredCitationId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const citationHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);
  const enableGraphRag = useAppStore((s) => s.enableGraphRag);
  const setGraphRagEnabled = useAppStore((s) => s.setGraphRagEnabled);
  const {
    sessions,
    activeSessionId,
    isStreaming,
    getActiveSession,
    createSession,
    selectSession,
    deleteSession,
    clearAll,
    addMessage,
    updateLastAssistant,
    finalizeLastAssistant,
    setStreaming,
  } = useChatStore();

  const activeSession = getActiveSession();
  const messages = activeSession?.messages || [];

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<{ collections: Collection[] }>("/collections"),
  });

  const visibleCollections = useMemo(
    () =>
      (collectionsData?.collections || []).filter(
        (c) => (c.total_chunks || c.chunk_count || c.total_documents || c.document_count || 0) > 0
      ),
    [collectionsData]
  );
  const collectionOptions = useMemo(
    () => Array.from(new Set(visibleCollections.map((c) => c.name).filter(Boolean))),
    [visibleCollections]
  );
  const starterQuestions = [
    "这门课有哪些高频考点？",
    "用表格总结本章核心概念",
    "根据当前资料出 5 道判断题",
  ];

  useEffect(() => {
    setCollectionDraft(activeSession?.collection || collection);
  }, [activeSession?.collection, collection]);

  useEffect(() => {
    if (collectionOptions.length === 0) return;
    if (collectionDraft && collectionOptions.includes(collectionDraft)) return;
    const next = collectionOptions[0];
    setCollectionDraft(next);
    setCollection(next);
  }, [collectionDraft, collectionOptions, setCollection]);

  useEffect(() => {
    const question = searchParams.get("q");
    if (!question) return;
    setInput(question);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const startNewChat = () => {
    const activeCollection = collectionDraft.trim() || collection || "default";
    setCollection(activeCollection);
    createSession(activeCollection);
    setInput("");
    setStatus("");
  };

  const showCitation = (id: string) => {
    if (citationHideTimerRef.current) {
      clearTimeout(citationHideTimerRef.current);
      citationHideTimerRef.current = null;
    }
    setHoveredCitationId(id);
  };

  const scheduleHideCitation = () => {
    if (citationHideTimerRef.current) {
      clearTimeout(citationHideTimerRef.current);
    }
    citationHideTimerRef.current = setTimeout(() => {
      setHoveredCitationId(null);
      citationHideTimerRef.current = null;
    }, 180);
  };

  const handleSend = async () => {
    const query = input.trim();
    if (!query || isStreaming) return;

    const activeCollection = collectionDraft.trim() || "default";
    setCollection(activeCollection);
    if (!activeSessionId) createSession(activeCollection);

    setInput("");
    setStatus(enableGraphRag ? "正在检索资料和知识图谱..." : enableRerank ? "正在检索资料并筛选重点..." : "正在检索当前科目的资料...");
    addMessage({ id: createId("msg"), role: "user", content: query }, activeCollection);
    addMessage(
      {
        id: createId("msg"),
        role: "assistant",
        content: enableGraphRag ? "正在检索资料和知识图谱..." : enableRerank ? "正在检索资料并筛选重点..." : "正在检索当前科目的资料...",
        isStreaming: true,
      },
      activeCollection
    );
    setStreaming(true);

    try {
      let streamedAnswer = "";
      await streamQuery(
        query,
        activeCollection,
        5,
        enableRerank,
        enableGraphRag,
        (stage) => {
          const message = stage.message || stage.stage;
          setStatus(message);
          if (!streamedAnswer) {
            updateLastAssistant(message);
          }
        },
        (text) => {
          streamedAnswer += text;
          updateLastAssistant(streamedAnswer);
        },
        (data) => {
          finalizeLastAssistant((data.citations || []) as Citation[]);
          setStatus("");
        },
        (err) => {
          updateLastAssistant(`查询失败：${err}`);
          finalizeLastAssistant([]);
          setStatus("");
        }
      );
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="hidden w-72 border-r bg-white md:flex md:flex-col">
        <div className="border-b p-3">
          <button
            onClick={startNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            <MessageSquarePlus size={16} />
            新建对话
          </button>
        </div>

        <div className="flex-1 overflow-auto p-2">
          {sessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-gray-400">暂无历史记录</div>
          ) : (
            <div className="space-y-1">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className={`group flex items-center gap-2 rounded-lg px-2 py-2 ${
                    session.id === activeSessionId ? "bg-gray-100" : "hover:bg-gray-50"
                  }`}
                >
                  <button
                    onClick={() => {
                      selectSession(session.id);
                      setCollection(session.collection);
                    }}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="truncate text-sm font-medium text-gray-800">{session.title}</div>
                    <div className="truncate text-xs text-gray-400">{session.collection}</div>
                  </button>
                  <button
                    title="删除这条历史"
                    onClick={() => deleteSession(session.id)}
                    className="rounded p-1 text-gray-300 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {sessions.length > 0 && (
          <div className="border-t p-3">
            <button
              onClick={clearAll}
              disabled={isStreaming}
              className="w-full rounded-lg border px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              清空全部历史
            </button>
          </div>
        )}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="border-b bg-white px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold text-gray-900">知识问答</h1>
              <div className="mt-1 text-xs text-gray-500">{status || "围绕当前科目的资料解释概念、总结重点和生成练习"}</div>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-600">
              <label className="flex items-center gap-2">
                资料库
                <select
                  value={collectionOptions.includes(collectionDraft) ? collectionDraft : ""}
                  onChange={(e) => {
                    const next = e.target.value;
                    setCollectionDraft(next);
                    if (next) setCollection(next);
                  }}
                  className="h-8 w-44 rounded-lg border px-2 text-sm text-gray-800"
                  disabled={isStreaming || collectionOptions.length === 0}
                >
                  {collectionOptions.length === 0 ? (
                    <option value="">暂无资料库</option>
                  ) : (
                    collectionOptions.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))
                  )}
                </select>
              </label>
              <div className="group relative flex items-center gap-1">
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={enableRerank}
                    onChange={(e) => setEnableRerank(e.target.checked)}
                    disabled={isStreaming}
                  />
                  深度筛选
                </label>
                <button
                  type="button"
                  aria-label="查看深度筛选说明"
                  className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                >
                  <HelpCircle size={15} />
                </button>
                <div className="pointer-events-none absolute right-0 top-full z-40 mt-2 hidden w-72 rounded-lg border bg-white p-3 text-xs leading-5 text-gray-600 shadow-lg group-hover:block group-focus-within:block">
                  <div className="mb-1 text-sm font-medium text-gray-900">深度筛选有什么用？</div>
                  <p>
                    开启后，系统会先检索更多候选片段，再让大模型按问题相关性重新排序，优先保留更适合作答和引用的内容。
                  </p>
                  <div className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-amber-700">
                    代价：会多一次大模型筛选步骤，回答通常更慢，并增加 API 调用消耗。
                  </div>
                </div>
              </div>
              <label className="flex items-center gap-2 rounded-full border px-2.5 py-1.5">
                <GitBranch size={14} className={enableGraphRag ? "text-blue-600" : "text-gray-400"} />
                <span>Graph-RAG</span>
                <input
                  type="checkbox"
                  checked={enableGraphRag}
                  onChange={(e) => setGraphRagEnabled(e.target.checked)}
                  disabled={isStreaming}
                />
              </label>
              <button
                onClick={startNewChat}
                className="rounded-lg border px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 md:hidden"
              >
                新对话
              </button>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-auto px-4 py-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 ? (
              <div className="pt-24 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-gray-900 text-white">
                  <Bot size={24} />
                </div>
                <h2 className="text-xl font-semibold text-gray-900">开始向当前科目提问</h2>
                <p className="mt-2 text-sm text-gray-500">
                  当前科目：{collectionDraft || "default"}。可以问概念、考试重点、章节总结或让助手出题。
                </p>
                <div className="mx-auto mt-6 grid max-w-2xl gap-2 text-left md:grid-cols-3">
                  {starterQuestions.map((question) => (
                    <button
                      key={question}
                      onClick={() => setInput(question)}
                      className="rounded-lg border bg-white px-3 py-3 text-sm text-gray-700 shadow-sm hover:border-blue-200 hover:bg-blue-50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white">
                      <Bot size={17} />
                    </div>
                  )}
                  <div
                    className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "border bg-white text-gray-900 shadow-sm"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        {msg.isStreaming && (
                          <div className="mt-2 h-1.5 w-24 overflow-hidden rounded-full bg-gray-100">
                            <div className="h-full w-1/2 animate-pulse rounded-full bg-blue-500" />
                          </div>
                        )}
                        {(() => {
                          const citedIndexes = extractCitedIndexes(msg.content);
                          const validCitations = (msg.citations || []).filter(
                            (c) => c.source || c.text_snippet || c.chunk_id
                          ).filter(
                            (c) => citedIndexes.size === 0 ? false : citedIndexes.has(c.index)
                          );
                          if (validCitations.length === 0) return null;

                          return (
                            <div className="mt-3 border-t border-gray-100 pt-3">
                              <div className="mb-2 text-xs font-medium text-gray-500">引用来源</div>
                              <div className="flex flex-wrap gap-1.5">
                                {validCitations.map((c) => {
                                  const citationId = `${msg.id}-${c.index}`;
                                  const isOpen = hoveredCitationId === citationId;
                                  return (
                                    <span
                                      key={citationId}
                                      className="relative inline-flex"
                                      onMouseEnter={() => showCitation(citationId)}
                                      onMouseLeave={scheduleHideCitation}
                                    >
                                      <button
                                        type="button"
                                        onFocus={() => showCitation(citationId)}
                                        onBlur={scheduleHideCitation}
                                        className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                                      >
                                        [{c.index}] {c.source ? c.source.split(/[/\\]/).pop() : "来源片段"}
                                      </button>
                                      {isOpen && (
                                        <div
                                          className="absolute left-0 top-full z-50 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-lg border bg-white p-3 text-xs text-gray-700 shadow-lg"
                                          onMouseEnter={() => showCitation(citationId)}
                                          onMouseLeave={scheduleHideCitation}
                                        >
                                          <div className="mb-1 font-medium text-gray-900">
                                            [{c.index}] {c.source ? c.source.split(/[/\\]/).pop() : "来源片段"}
                                            {c.page ? ` · p.${c.page}` : ""}
                                          </div>
                                          {c.text_snippet ? (
                                            <div className="max-h-40 overflow-y-auto pr-2 leading-5 text-gray-600 [scrollbar-gutter:stable]">{c.text_snippet}</div>
                                          ) : (
                                            <div className="text-gray-500">没有可显示的片段详情。</div>
                                          )}
                                        </div>
                                      )}
                                    </span>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white">
                      <UserRound size={17} />
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="border-t bg-white px-4 py-4">
          <form
            className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-white p-2 shadow-sm"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="问概念、公式、例题、考试重点..."
              rows={1}
              className="max-h-32 min-h-10 flex-1 resize-none border-0 px-3 py-2 text-sm outline-none"
              disabled={isStreaming}
            />
            <button
              type="submit"
              disabled={isStreaming || !input.trim()}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-900 text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send size={18} />
            </button>
          </form>
        </footer>
      </section>
    </div>
  );
}
