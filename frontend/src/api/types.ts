export interface Collection {
  name: string;
  collection?: string;
  chunk_count?: number;
  document_count?: number;
  image_count?: number;
  total_chunks?: number;
  total_documents?: number;
  total_images?: number;
}

export interface Document {
  source_path: string;
  source_hash: string;
  collection: string;
  chunk_count: number;
  image_count: number;
  processed_at: string;
}

export interface Chunk {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface Citation {
  index: number;
  chunk_id?: string;
  source: string;
  score: number;
  text_snippet: string;
  page?: number;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  metadata: Record<string, unknown>;
  is_empty: boolean;
}

export interface PipelineResult {
  success: boolean;
  file_path: string;
  doc_id: string;
  chunk_count: number;
  image_count: number;
  vector_ids_count: number;
  error?: string;
  stages: Record<string, unknown>;
}

export interface ComponentInfo {
  name: string;
  provider: string;
  model: string;
  extra: Record<string, unknown>;
}

export interface Trace {
  trace_id: string;
  trace_type: string;
  started_at: string;
  stages?: Array<{
    stage: string;
    timestamp: string;
    elapsed_ms: number;
    data: Record<string, unknown>;
  }>;
  metadata?: Record<string, unknown>;
}

export interface KnowledgePoint {
  id: string;
  text?: string;
  content?: string;
  category: string;
  importance: string | number;
  source_chunk_id?: string;
  source_ref?: string;
  chunk_id?: string;
}

export interface MasteryStats {
  total: number;
  mastered: number;
  learning: number;
  needs_review: number;
}

export interface ReviewItem {
  knowledge_point_id: string;
  content: string;
  category?: string;
  importance?: string | number;
  source_ref?: string;
  chunk_id?: string;
  interval_days: number;
  ease_factor: number;
  last_quality?: number;
  next_review_at?: string;
  next_review_time?: string;
}

export interface QuizQuestion {
  question: string;
  type: "mcq" | "true_false" | "short_answer";
  options?: string[];
  correct_answer: string;
  explanation: string;
}

export interface IngestionProgress {
  stage: string;
  current: number;
  total: number;
}
