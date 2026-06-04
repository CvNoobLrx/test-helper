import { useEffect, useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, uploadFile } from "../api/client";
import { useAppStore } from "../stores/appStore";
import type { Collection, Document, IngestionProgress, PipelineResult } from "../api/types";
import { BookMarked, File, Plus, Trash2, Upload } from "lucide-react";

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const selectedCollection = useAppStore((s) => s.selectedCollection);
  const setSelectedCollection = useAppStore((s) => s.setCollection);
  const [collection, setCollection] = useState(selectedCollection);
  const [localSubjects, setLocalSubjects] = useState<string[]>([]);
  const [newSubject, setNewSubject] = useState("");
  const [addingSubject, setAddingSubject] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [result, setResult] = useState<PipelineResult | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("final-review-helper-subjects") || "[]");
      if (Array.isArray(saved)) {
        setLocalSubjects(saved.filter((item) => typeof item === "string"));
      }
    } catch {
      setLocalSubjects([]);
    }
  }, []);

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<{ collections: Collection[] }>("/collections"),
  });

  const { data: docsData } = useQuery({
    queryKey: ["documents", collection],
    queryFn: () => api.get<{ documents: Document[] }>(`/documents?collection=${encodeURIComponent(collection)}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => api.del(`/documents/${docId}?collection=${encodeURIComponent(collection)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["collections"] });
    },
  });

  const subjectOptions = Array.from(
    new Set([
      "default",
      selectedCollection,
      collection,
      ...localSubjects,
      ...(collectionsData?.collections || []).map((c) => c.name),
    ].filter(Boolean))
  );

  const handleSelectCollection = (value: string) => {
    const next = value || "default";
    setCollection(next);
    setSelectedCollection(next);
  };

  const handleAddSubject = () => {
    const subject = newSubject.trim();
    if (!subject) return;
    setLocalSubjects((items) => {
      const next = Array.from(new Set([...items, subject]));
      localStorage.setItem("final-review-helper-subjects", JSON.stringify(next));
      return next;
    });
    handleSelectCollection(subject);
    setNewSubject("");
    setAddingSubject(false);
  };

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setProgress(null);
    setResult(null);

    await uploadFile(
      file,
      collection,
      (p) => setProgress(p),
      (r) => { setResult(r as PipelineResult); setUploading(false); },
      (e) => { setResult({ success: false, error: e } as PipelineResult); setUploading(false); }
    );

    setSelectedCollection(collection.trim() || "default");
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["collections"] });
  };

  const documents = docsData?.documents || [];

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-950">复习资料</h1>
        <p className="mt-2 text-sm text-gray-500">按科目整理课件、教材和笔记，上传后会自动拆分为可检索的复习片段。</p>
      </div>

      <div className="mb-6 rounded-xl border bg-white p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <BookMarked size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-950">添加课程资料</h2>
            <p className="text-sm text-gray-500">支持 PDF、PPT、Word、图片和文本资料。</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.pptx,.txt,.md,.docx,.png,.jpg,.jpeg"
            className="block text-sm text-gray-500 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-blue-700 hover:file:bg-blue-100"
          />
          <select
            value={collection}
            onChange={(e) => handleSelectCollection(e.target.value)}
            className="h-10 w-48 rounded-lg border bg-white px-3 text-sm text-gray-900"
          >
            {subjectOptions.map((subject) => (
              <option key={subject} value={subject}>{subject}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setAddingSubject((v) => !v)}
            className="flex h-10 items-center gap-1 rounded-lg border px-3 text-sm text-gray-700 hover:bg-gray-50"
          >
            <Plus size={15} />
            新科目
          </button>
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload size={16} />
            {uploading ? "正在解析" : "上传资料"}
          </button>
        </div>

        {addingSubject && (
          <div className="mt-4 flex max-w-md items-center gap-2">
            <input
              value={newSubject}
              onChange={(e) => setNewSubject(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddSubject();
                }
              }}
              placeholder="例如：论文写作基础、高等数学"
              className="flex-1 px-3 py-2 border rounded-lg text-sm"
            />
            <button
              type="button"
              onClick={handleAddSubject}
              className="px-3 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
            >
              添加科目
            </button>
          </div>
        )}

        {progress && (
          <div className="mt-4">
            <div className="flex justify-between text-sm text-gray-600 mb-1">
              <span>{progress.stage}</span>
              <span>{progress.current}/{progress.total}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {result && (
          <div className={`mt-4 p-3 rounded-lg text-sm ${result.success ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
            {result.success
              ? `解析完成：生成 ${result.chunk_count} 个复习片段，识别 ${result.image_count} 张图片。`
              : `上传失败：${result.error}`}
          </div>
        )}
      </div>

      <div className="rounded-xl border bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-950">当前科目资料 ({documents.length})</h2>
          <span className="text-sm text-gray-500">{collection || "default"}</span>
        </div>
        {documents.length === 0 ? (
          <div className="rounded-lg bg-gray-50 p-6 text-center text-sm text-gray-500">
            当前科目还没有资料。先上传一份课件或教材，助手才能基于资料回答问题。
          </div>
        ) : (
          <div className="divide-y">
            {documents.map((doc) => (
              <div key={doc.source_hash} className="py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <File size={18} className="text-gray-400" />
                  <div>
                    <div className="font-medium text-sm">{doc.source_path.split(/[/\\]/).pop()}</div>
                    <div className="text-xs text-gray-500">
                      {doc.chunk_count} 个片段 · {doc.image_count} 张图片 · {doc.processed_at?.slice(0, 19)}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(doc.source_hash)}
                  className="p-2 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
