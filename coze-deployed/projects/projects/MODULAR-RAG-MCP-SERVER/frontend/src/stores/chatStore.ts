import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Citation } from "../api/types";
import { createId } from "../utils/id";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  error?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  collection: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isStreaming: boolean;
  getActiveSession: () => ChatSession | undefined;
  createSession: (collection: string) => string;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => void;
  clearAll: () => void;
  addMessage: (msg: ChatMessage, collection: string) => void;
  updateLastAssistant: (content: string) => void;
  finalizeLastAssistant: (citations: Citation[]) => void;
  setStreaming: (v: boolean) => void;
}

function now() {
  return new Date().toISOString();
}

function titleFrom(content: string) {
  const compact = content.replace(/\s+/g, " ").trim();
  return compact.length > 22 ? `${compact.slice(0, 22)}...` : compact || "新对话";
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isStreaming: false,
      getActiveSession: () => {
        const { sessions, activeSessionId } = get();
        return sessions.find((s) => s.id === activeSessionId);
      },
      createSession: (collection) => {
        const id = createId("chat");
        const ts = now();
        const session: ChatSession = {
          id,
          title: "新对话",
          collection,
          createdAt: ts,
          updatedAt: ts,
          messages: [],
        };
        set((s) => ({
          sessions: [session, ...s.sessions],
          activeSessionId: id,
        }));
        return id;
      },
      selectSession: (id) => set({ activeSessionId: id }),
      deleteSession: (id) =>
        set((s) => {
          const sessions = s.sessions.filter((session) => session.id !== id);
          return {
            sessions,
            activeSessionId:
              s.activeSessionId === id ? sessions[0]?.id ?? null : s.activeSessionId,
            isStreaming: s.activeSessionId === id ? false : s.isStreaming,
          };
        }),
      clearAll: () => set({ sessions: [], activeSessionId: null, isStreaming: false }),
      addMessage: (msg, collection) =>
        set((s) => {
          let activeSessionId = s.activeSessionId;
          let sessions = s.sessions;
          const ts = now();

          if (!activeSessionId || !sessions.some((session) => session.id === activeSessionId)) {
            activeSessionId = createId("chat");
            sessions = [
              {
                id: activeSessionId,
                title: msg.role === "user" ? titleFrom(msg.content) : "新对话",
                collection,
                createdAt: ts,
                updatedAt: ts,
                messages: [],
              },
              ...sessions,
            ];
          }

          sessions = sessions.map((session) => {
            if (session.id !== activeSessionId) return session;
            const shouldTitle = session.title === "新对话" && msg.role === "user";
            return {
              ...session,
              title: shouldTitle ? titleFrom(msg.content) : session.title,
              collection,
              updatedAt: ts,
              messages: [...session.messages, msg],
            };
          });

          return { sessions, activeSessionId };
        }),
      updateLastAssistant: (content) =>
        set((s) => ({
          sessions: s.sessions.map((session) => {
            if (session.id !== s.activeSessionId) return session;
            const messages = [...session.messages];
            const last = messages[messages.length - 1];
            if (last?.role === "assistant") {
              messages[messages.length - 1] = { ...last, content };
            }
            return { ...session, messages, updatedAt: now() };
          }),
        })),
      finalizeLastAssistant: (citations) =>
        set((s) => ({
          sessions: s.sessions.map((session) => {
            if (session.id !== s.activeSessionId) return session;
            const messages = [...session.messages];
            const last = messages[messages.length - 1];
            if (last?.role === "assistant") {
              messages[messages.length - 1] = { ...last, citations, isStreaming: false };
            }
            return { ...session, messages, updatedAt: now() };
          }),
          isStreaming: false,
        })),
      setStreaming: (v) => set({ isStreaming: v }),
    }),
    {
      name: "final-review-helper-chat",
      partialize: (state) => ({
        sessions: state.sessions,
        activeSessionId: state.activeSessionId,
      }),
    }
  )
);
