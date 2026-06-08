import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { AlertCircle, CheckCircle2, LoaderCircle, Upload, X } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { useAppStore } from "../../stores/appStore";

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <GlobalUploadStatus />
        <Outlet />
      </main>
    </div>
  );
}

function GlobalUploadStatus() {
  const upload = useAppStore((s) => s.upload);
  const clearUpload = useAppStore((s) => s.clearUpload);

  useEffect(() => {
    if (!upload.result?.success) {
      return;
    }

    const timer = window.setTimeout(clearUpload, 2500);
    return () => window.clearTimeout(timer);
  }, [clearUpload, upload.result?.success]);

  if (!upload.uploading && !upload.result) {
    return null;
  }

  const progressValue = upload.progress
    ? Math.round((upload.progress.current / upload.progress.total) * 100)
    : upload.uploading
      ? 5
      : 100;
  const isError = upload.result && !upload.result.success;

  return (
    <div className="sticky top-0 z-40 border-b bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${isError ? "bg-red-50 text-red-600" : upload.result ? "bg-green-50 text-green-600" : "bg-blue-50 text-blue-600"}`}>
          {isError ? <AlertCircle size={18} /> : upload.result ? <CheckCircle2 size={18} /> : <Upload size={18} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="truncate text-sm font-medium text-gray-900">
              {upload.uploading ? "正在解析" : upload.result?.success ? "解析完成" : "解析失败"}：{upload.fileName || "资料"}
            </div>
            <div className="text-xs text-gray-500">
              {upload.progress ? `${upload.progress.stage} · ${upload.progress.current}/${upload.progress.total}` : upload.collection}
            </div>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className={`h-full rounded-full transition-all ${isError ? "bg-red-500" : upload.result ? "bg-green-500" : "bg-blue-600"}`}
              style={{ width: `${progressValue}%` }}
            />
          </div>
          {upload.result && (
            <div className={`mt-2 text-xs ${upload.result.success ? "text-green-700" : "text-red-700"}`}>
              {upload.result.success
                ? `生成 ${upload.result.chunk_count} 个片段，识别 ${upload.result.image_count} 张图片。`
                : upload.result.error || "上传失败"}
            </div>
          )}
        </div>
        {upload.uploading ? (
          <div
            className="flex h-9 w-9 items-center justify-center rounded-lg text-blue-600"
            aria-label="正在解析"
          >
            <LoaderCircle size={20} className="animate-spin" />
          </div>
        ) : upload.result?.success ? (
          <div
            className="flex h-9 w-9 items-center justify-center rounded-lg text-green-600"
            aria-label="解析完成"
          >
            <CheckCircle2 size={20} />
          </div>
        ) : (
          <button
            type="button"
            onClick={clearUpload}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="关闭上传状态"
          >
            <X size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
