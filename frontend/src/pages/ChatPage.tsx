import { useState, useRef, useEffect } from "react";
import { useChatStore } from "../stores/chatStore";
import { useAppStore } from "../stores/appStore";
import { api, streamQuery } from "../api/client";
import { Send, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation, Collection } from "../api/types";
import { useQuery } from "@tanstack/react-query";

export function ChatPage() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [collectionDraft, setCollectionDraft] = useState("");
  const { messages, isStreaming, addMessage, updateLastAssistant, finalizeLastAssistant, setStreaming, clear } = useChatStore();
  const collection = useAppStore((s) => s.selectedCollection);
  const setCollection = useAppStore((s) => s.setCollection);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<{ collections: Collection[] }>("/collections"),
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    setCollectionDraft(collection);
  }, [collection]);

  const handleSend = async () => {
    const query = input.trim();
    if (!query || isStreaming) return;
    const activeCollection = collectionDraft.trim() || "default";
    setCollection(activeCollection);

    setInput("");
    addMessage({ id: crypto.randomUUID(), role: "user", content: query });
    addMessage({ id: crypto.randomUUID(), role: "assistant", content: "", isStreaming: true });
    setStreaming(true);
    setStatus("正在检索资料库...");

    try {
      await streamQuery(
        query,
        activeCollection,
        5,
        (stage) => setStatus(stage.message || stage.stage),
        (text) => updateLastAssistant(text),
        (data) => {
          finalizeLastAssistant((data.citations || []) as Citation[]);
          setStatus("");
        },
        (err) => {
          updateLastAssistant(`Error: ${err}`);
          finalizeLastAssistant([]);
          setStatus("");
        }
      );
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center justify-between px-6 py-3 border-b bg-white">
        <div>
          <h1 className="text-lg font-semibold">知识问答</h1>
          <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
            <span>资料库</span>
            <input
              list="chat-collections"
              value={collectionDraft}
              onChange={(e) => setCollectionDraft(e.target.value)}
              onBlur={() => setCollection(collectionDraft.trim() || "default")}
              className="h-7 w-44 rounded border px-2 text-xs text-gray-700"
              disabled={isStreaming}
            />
            <datalist id="chat-collections">
              {(collectionsData?.collections || []).map((c) => (
                <option key={c.name} value={c.name} />
              ))}
            </datalist>
            {status && <span>{status}</span>}
          </div>
        </div>
        <button title="清空对话" onClick={clear} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
          <Trash2 size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg">向期末复习资料提问</p>
            <p className="text-sm mt-1">当前资料库：{collectionDraft || collection}</p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white border"
              }`}
            >
              {msg.role === "assistant" ? (
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || "..."}</ReactMarkdown>
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-gray-100">
                      <div className="text-xs text-gray-500 font-medium mb-1">引用来源</div>
                      <div className="flex flex-wrap gap-1">
                        {msg.citations.map((c, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700"
                            title={`${c.source} (score: ${c.score.toFixed(3)})`}
                          >
                            [{c.index}]
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm">{msg.content}</p>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="px-6 py-4 border-t bg-white">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="输入要复习的问题..."
            className="flex-1 px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isStreaming}
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
