import { create } from "zustand";

interface AppState {
  selectedCollection: string;
  sidebarOpen: boolean;
  setCollection: (c: string) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedCollection: "default",
  sidebarOpen: true,
  setCollection: (c) => set({ selectedCollection: c }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
