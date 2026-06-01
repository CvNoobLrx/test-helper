import { create } from "zustand";
import type { Citation } from "../api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  error?: string;
}

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistant: (content: string) => void;
  finalizeLastAssistant: (citations: Citation[]) => void;
  setStreaming: (v: boolean) => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastAssistant: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content };
      }
      return { messages: msgs };
    }),
  finalizeLastAssistant: (citations) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, citations, isStreaming: false };
      }
      return { messages: msgs, isStreaming: false };
    }),
  setStreaming: (v) => set({ isStreaming: v }),
  clear: () => set({ messages: [], isStreaming: false }),
}));
