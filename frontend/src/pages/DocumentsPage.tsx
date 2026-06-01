import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, uploadFile } from "../api/client";
import type { Document, IngestionProgress, PipelineResult } from "../api/types";
import { Upload, Trash2, File } from "lucide-react";

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [collection, setCollection] = useState("default");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [result, setResult] = useState<PipelineResult | null>(null);

  const { data: docsData } = useQuery({
    queryKey: ["documents", collection],
    queryFn: () => api.get<{ documents: Document[] }>(`/documents?collection=${collection}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => api.del(`/documents/${docId}?collection=${collection}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

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

    queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const documents = docsData?.documents || [];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Documents</h1>

      {/* Upload section */}
      <div className="bg-white rounded-xl border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Upload Document</h2>
        <div className="flex items-center gap-4">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.pptx,.txt,.md,.docx,.png,.jpg,.jpeg"
            className="block text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
          <input
            type="text"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            placeholder="Collection"
            className="px-3 py-2 border rounded-lg text-sm w-40"
          />
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload size={16} />
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </div>

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
              ? `Success: ${result.chunk_count} chunks, ${result.image_count} images`
              : `Error: ${result.error}`}
          </div>
        )}
      </div>

      {/* Document list */}
      <div className="bg-white rounded-xl border p-6">
        <h2 className="text-lg font-semibold mb-4">Ingested Documents ({documents.length})</h2>
        {documents.length === 0 ? (
          <p className="text-gray-500 text-sm">No documents in this collection.</p>
        ) : (
          <div className="divide-y">
            {documents.map((doc) => (
              <div key={doc.source_hash} className="py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <File size={18} className="text-gray-400" />
                  <div>
                    <div className="font-medium text-sm">{doc.source_path.split(/[/\\]/).pop()}</div>
                    <div className="text-xs text-gray-500">
                      {doc.chunk_count} chunks · {doc.image_count} images · {doc.processed_at?.slice(0, 19)}
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
