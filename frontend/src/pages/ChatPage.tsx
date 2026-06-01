import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, MessageSquarePlus, Send, Trash2, UserRound } from "lucide-react";
import { api, streamQuery } from "../api/client";
import type { Citation, Collection } from "../api/types";
import { useAppStore } from "../stores/appStore";
import { useChatStore } from "../stores/chatStore";
import { createId } from "../utils/id";

export function ChatPage() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [collectionDraft, setCollectionDraft] = useState("");
  const [enableRerank, setEnableRerank] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);
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

  useEffect(() => {
    setCollectionDraft(activeSession?.collection || collection);
  }, [activeSession?.collection, collection]);

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

  const handleSend = async () => {
    const query = input.trim();
    if (!query || isStreaming) return;

    const activeCollection = collectionDraft.trim() || "default";
    setCollection(activeCollection);
    if (!activeSessionId) createSession(activeCollection);

    setInput("");
    setStatus(enableRerank ? "正在检索并进行 LLM 重排..." : "正在检索资料库...");
    addMessage({ id: createId("msg"), role: "user", content: query }, activeCollection);
    addMessage(
      {
        id: createId("msg"),
        role: "assistant",
        content: enableRerank ? "正在检索并进行 LLM 重排..." : "正在检索资料库...",
        isStreaming: true,
      },
      activeCollection
    );
    setStreaming(true);

    try {
      await streamQuery(
        query,
        activeCollection,
        5,
        enableRerank,
        (stage) => {
          const message = stage.message || stage.stage;
          setStatus(message);
          updateLastAssistant(message);
        },
        (text) => updateLastAssistant(text),
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
              <div className="mt-1 text-xs text-gray-500">{status || "基于当前资料库回答问题"}</div>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-600">
              <label className="flex items-center gap-2">
                资料库
                <input
                  list="chat-collections"
                  value={collectionDraft}
                  onChange={(e) => setCollectionDraft(e.target.value)}
                  onBlur={() => setCollection(collectionDraft.trim() || "default")}
                  className="h-8 w-44 rounded-lg border px-2 text-sm text-gray-800"
                  disabled={isStreaming}
                />
              </label>
              <datalist id="chat-collections">
                {visibleCollections.map((c) => (
                  <option key={c.name} value={c.name} />
                ))}
              </datalist>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={enableRerank}
                  onChange={(e) => setEnableRerank(e.target.checked)}
                  disabled={isStreaming}
                />
                LLM重排
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
                <h2 className="text-xl font-semibold text-gray-900">开始向资料提问</h2>
                <p className="mt-2 text-sm text-gray-500">
                  当前资料库：{collectionDraft || "default"}。发送问题后会立即显示检索状态和回答。
                </p>
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
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="mt-3 border-t border-gray-100 pt-2">
                            <div className="mb-1 text-xs font-medium text-gray-500">引用来源</div>
                            <div className="flex flex-wrap gap-1">
                              {msg.citations.map((c, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                                  title={`${c.source} (score: ${Number(c.score || 0).toFixed(3)})`}
                                >
                                  [{c.index}]
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
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
              placeholder="输入要复习的问题..."
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
