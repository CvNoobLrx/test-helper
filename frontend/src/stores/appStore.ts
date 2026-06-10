import { create } from "zustand";

import type { IngestionProgress, PipelineResult } from "../api/types";

interface AppState {
  selectedCollection: string;
  sidebarOpen: boolean;
  enableGraphRag: boolean;
  upload: {
    fileName: string;
    collection: string;
    uploading: boolean;
    progress: IngestionProgress | null;
    result: PipelineResult | null;
  };
  setCollection: (c: string) => void;
  setGraphRagEnabled: (enabled: boolean) => void;
  toggleSidebar: () => void;
  startUpload: (fileName: string, collection: string) => void;
  setUploadProgress: (progress: IngestionProgress) => void;
  finishUpload: (result: PipelineResult) => void;
  clearUpload: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedCollection: "default",
  sidebarOpen: true,
  enableGraphRag: false,
  upload: {
    fileName: "",
    collection: "default",
    uploading: false,
    progress: null,
    result: null,
  },
  setCollection: (c) => set({ selectedCollection: c }),
  setGraphRagEnabled: (enabled) => set({ enableGraphRag: enabled }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  startUpload: (fileName, collection) =>
    set({
      upload: {
        fileName,
        collection,
        uploading: true,
        progress: null,
        result: null,
      },
    }),
  setUploadProgress: (progress) =>
    set((state) => ({
      upload: {
        ...state.upload,
        uploading: true,
        progress,
      },
    })),
  finishUpload: (result) =>
    set((state) => ({
      upload: {
        ...state.upload,
        uploading: false,
        result,
      },
    })),
  clearUpload: () =>
    set((state) => ({
      upload: {
        ...state.upload,
        uploading: false,
        progress: null,
        result: null,
      },
    })),
}));
