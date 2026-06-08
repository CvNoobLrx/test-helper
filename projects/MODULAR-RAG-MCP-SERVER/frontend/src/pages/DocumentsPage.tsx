import { useEffect, useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, uploadFile } from "../api/client";
import { useAppStore } from "../stores/appStore";
import type { Collection, Document, DocumentPreview, PipelineResult } from "../api/types";
import { BookMarked, Download, ExternalLink, Eye, File, FileText, Plus, Trash2, Upload, X } from "lucide-react";

type PreviewMode = "original" | "markdown";

const textPreviewExtensions = new Set([".md", ".txt", ".csv", ".json", ".log"]);
const pdfPreviewExtensions = new Set([".pdf"]);

function getFileName(path: string) {
  return path.split(/[/\\]/).pop() || path;
}

function getExtension(path: string) {
  const fileName = getFileName(path).toLowerCase();
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex) : "";
}

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const selectedCollection = useAppStore((s) => s.selectedCollection);
  const setSelectedCollection = useAppStore((s) => s.setCollection);
  const upload = useAppStore((s) => s.upload);
  const startUpload = useAppStore((s) => s.startUpload);
  const setUploadProgress = useAppStore((s) => s.setUploadProgress);
  const finishUpload = useAppStore((s) => s.finishUpload);
  const [collection, setCollection] = useState(selectedCollection);
  const [localSubjects, setLocalSubjects] = useState<string[]>([]);
  const [newSubject, setNewSubject] = useState("");
  const [addingSubject, setAddingSubject] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("original");
  const [originalText, setOriginalText] = useState("");
  const [originalTextError, setOriginalTextError] = useState("");
  const [loadingOriginalText, setLoadingOriginalText] = useState(false);

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

  const { data: previewData, isLoading: previewLoading, error: previewError } = useQuery({
    queryKey: ["document-preview", collection, previewDoc?.source_hash],
    queryFn: () =>
      api.get<DocumentPreview>(
        `/documents/${encodeURIComponent(previewDoc!.source_hash)}/preview?collection=${encodeURIComponent(collection)}`
      ),
    enabled: Boolean(previewDoc),
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
    const targetCollection = collection.trim() || "default";
    startUpload(file.name, targetCollection);

    await uploadFile(
      file,
      targetCollection,
      (p) => setUploadProgress(p),
      (r) => finishUpload(r as PipelineResult),
      (e) => finishUpload({ success: false, error: e } as PipelineResult)
    );

    setSelectedCollection(targetCollection);
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["collections"] });
    queryClient.invalidateQueries({ queryKey: ["document-preview"] });
  };

  const handlePreview = (doc: Document) => {
    setPreviewDoc(doc);
    setPreviewMode("original");
    setOriginalText("");
    setOriginalTextError("");
  };

  const handleClosePreview = () => {
    setPreviewDoc(null);
    setOriginalText("");
    setOriginalTextError("");
  };

  const originalExtension = previewData?.extension || (previewDoc ? getExtension(previewDoc.source_path) : "");
  const canPreviewOriginalAsText = textPreviewExtensions.has(originalExtension);
  const canPreviewOriginalAsPdf = pdfPreviewExtensions.has(originalExtension);
  const originalUrl = previewData?.original_url || "";

  const documents = docsData?.documents || [];

  useEffect(() => {
    if (!previewDoc || previewMode !== "original" || !previewData || !canPreviewOriginalAsText) {
      return;
    }

    let cancelled = false;
    setLoadingOriginalText(true);
    setOriginalTextError("");
    fetch(previewData.original_url)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`原文加载失败：${res.status}`);
        }
        return res.text();
      })
      .then((text) => {
        if (!cancelled) {
          setOriginalText(text);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setOriginalTextError(String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingOriginalText(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [canPreviewOriginalAsText, previewData, previewDoc, previewMode]);

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
            disabled={upload.uploading}
            className="flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload size={16} />
            {upload.uploading ? "正在解析" : "上传资料"}
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

        {upload.progress && (
          <div className="mt-4">
            <div className="flex justify-between text-sm text-gray-600 mb-1">
              <span>{upload.progress.stage}</span>
              <span>{upload.progress.current}/{upload.progress.total}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${(upload.progress.current / upload.progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {upload.result && (
          <div className={`mt-4 p-3 rounded-lg text-sm ${upload.result.success ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
            {upload.result.success
              ? `解析完成：生成 ${upload.result.chunk_count} 个复习片段，识别 ${upload.result.image_count} 张图片。`
              : `上传失败：${upload.result.error}`}
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
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => handlePreview(doc)}
                    className="flex h-9 items-center gap-1 rounded-lg border px-3 text-sm text-blue-700 hover:bg-blue-50"
                  >
                    <Eye size={15} />
                    预览
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate(doc.source_hash)}
                    className="p-2 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50"
                    aria-label="删除资料"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {previewDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/45 p-4">
          <div className="flex max-h-[86vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <FileText size={18} className="shrink-0 text-blue-600" />
                  <h3 className="truncate text-base font-semibold text-gray-950">
                    {previewData?.filename || getFileName(previewDoc.source_path)}
                  </h3>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {previewDoc.chunk_count} 个片段 · {previewDoc.image_count} 张图片
                </p>
              </div>
              <button
                type="button"
                onClick={handleClosePreview}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                aria-label="关闭预览"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-gray-50 px-5 py-3">
              <div className="inline-flex rounded-lg border bg-white p-1">
                <button
                  type="button"
                  onClick={() => setPreviewMode("original")}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                    previewMode === "original"
                      ? "bg-blue-600 text-white"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  原文
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode("markdown")}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                    previewMode === "markdown"
                      ? "bg-blue-600 text-white"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  转换后内容
                </button>
              </div>

              {originalUrl && (
                <div className="flex items-center gap-2">
                  <a
                    href={originalUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex h-9 items-center gap-1 rounded-lg border bg-white px-3 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    <ExternalLink size={15} />
                    新窗口打开
                  </a>
                  <a
                    href={originalUrl}
                    download
                    className="flex h-9 items-center gap-1 rounded-lg border bg-white px-3 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    <Download size={15} />
                    下载
                  </a>
                </div>
              )}
            </div>

            <div className="min-h-0 flex-1 overflow-auto bg-white p-5">
              {previewLoading && (
                <div className="rounded-lg bg-gray-50 p-6 text-center text-sm text-gray-500">正在加载预览...</div>
              )}

              {previewError && (
                <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
                  预览加载失败：{String(previewError)}
                </div>
              )}

              {!previewLoading && !previewError && previewMode === "original" && canPreviewOriginalAsPdf && (
                <iframe
                  title="原文预览"
                  src={originalUrl}
                  className="h-[64vh] w-full rounded-lg border"
                />
              )}

              {!previewLoading && !previewError && previewMode === "original" && canPreviewOriginalAsText && (
                <div className="rounded-lg border bg-gray-50 p-4">
                  {loadingOriginalText ? (
                    <div className="text-sm text-gray-500">正在加载原文...</div>
                  ) : originalTextError ? (
                    <div className="text-sm text-red-700">{originalTextError}</div>
                  ) : (
                    <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-800">{originalText}</pre>
                  )}
                </div>
              )}

              {!previewLoading &&
                !previewError &&
                previewMode === "original" &&
                !canPreviewOriginalAsPdf &&
                !canPreviewOriginalAsText && (
                  <div className="rounded-lg border bg-gray-50 p-8 text-center">
                    <FileText size={34} className="mx-auto mb-3 text-gray-400" />
                    <div className="text-sm font-medium text-gray-800">当前格式暂不支持浏览器内原文预览</div>
                    <p className="mt-2 text-sm text-gray-500">可以在新窗口打开或下载原文件，也可以切换查看转换后的 Markdown 内容。</p>
                  </div>
                )}

              {!previewLoading && !previewError && previewMode === "markdown" && (
                previewData?.markdown ? (
                  <div className="max-w-none rounded-lg border px-5 py-4 text-sm leading-7 text-gray-800">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{previewData.markdown}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="rounded-lg bg-gray-50 p-6 text-center text-sm text-gray-500">
                    暂无可预览的转换后内容。
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
