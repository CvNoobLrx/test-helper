import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Collection, ComponentInfo } from "../api/types";
import { FileText, Database, Layers, Activity } from "lucide-react";

export function DashboardPage() {
  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<{ collections: Collection[] }>("/collections"),
  });

  const { data: configData } = useQuery({
    queryKey: ["config"],
    queryFn: () => api.get<{ components: ComponentInfo[] }>("/monitoring/config"),
  });

  const collections = collectionsData?.collections || [];
  const totalChunks = collections.reduce((sum, c) => sum + (c.total_chunks || 0), 0);
  const totalDocs = collections.reduce((sum, c) => sum + (c.total_documents || 0), 0);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">复习总览</h1>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard icon={Database} label="资料库" value={collections.length} />
        <StatCard icon={FileText} label="文档" value={totalDocs} />
        <StatCard icon={Layers} label="知识片段" value={totalChunks} />
        <StatCard icon={Activity} label="组件" value={configData?.components?.length || 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-6">
          <h2 className="text-lg font-semibold mb-4">资料库</h2>
          {collections.length === 0 ? (
            <p className="text-gray-500 text-sm">还没有资料库。上传教材 PDF 或课件 PPT 后开始复习。</p>
          ) : (
            <div className="space-y-3">
              {collections.map((c) => (
                <div key={c.name} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="font-medium">{c.name}</span>
                  <span className="text-sm text-gray-500">{c.total_chunks || 0} 个片段</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border p-6">
          <h2 className="text-lg font-semibold mb-4">系统组件</h2>
          {configData?.components?.length ? (
            <div className="space-y-3">
              {configData.components.map((c) => (
                <div key={c.name} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="font-medium">{c.name}</span>
                  <span className="text-sm text-gray-500">{c.provider} / {c.model}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">加载中...</p>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: number }) {
  return (
    <div className="bg-white rounded-xl border p-5">
      <div className="flex items-center gap-3 mb-2">
        <Icon size={20} className="text-gray-400" />
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );
}
