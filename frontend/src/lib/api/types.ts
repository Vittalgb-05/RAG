export type HealthStatus = "healthy" | "loading" | "unreachable" | "offline";

export interface Health {
  status: HealthStatus;
  message: string;
  ready: boolean;
  mode: "local" | "cloud";
  provider: string;
  model: string;
  capabilities: {
    context_window: number;
    supports_vision: boolean;
    supports_streaming: boolean;
  };
  runtime: {
    llama_server_version: string | null;
    build: string | null;
  };
}

export interface Telemetry {
  gpu: { total_mb: number; used_mb: number; free_mb: number } | null;
  process: { rss_mb: number; vms_mb: number };
  inference: { busy: boolean };
  ts: string;
}

export interface AppSettings {
  mode: "local" | "cloud";
  egress_policy: "local" | "cloud";
  limits: {
    max_file_mb: number;
    max_pages: number;
    max_chat_turns: number;
  };
  cloud: {
    enabled: boolean;
    provider: "groq" | "openai" | "anthropic";
    model: string;
    consented: boolean;
    has_key: boolean;
  };
}

export interface DocumentSummary {
  doc_id: string;
  filename: string;
  sha256: string;
  status: "indexing" | "indexed" | "failed";
  pages: number;
  chunks: number;
  evidence_elements: number;
  size_bytes: number;
  created_at: string;
  has_vectors: boolean;
}

export interface DocumentDetail {
  doc_id: string;
  filename: string;
  sha256: string;
  status: string;
  num_pages: number;
  num_chunks: number;
  size_bytes: number;
  upload_time: string;
  chunks: Array<{ page: number; content: string; [key: string]: any }>;
  evidence: Array<{ kind: string; page: number; content: string; [key: string]: any }>;
}

export type JobKind = "ingest" | "reindex" | "summarize";

export interface Job {
  job_id: string;
  kind: JobKind;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  pct: number | null;
  message: string;
  result?: unknown;
  error?: Problem;
  created_at?: string;
  updated_at?: string;
}

export type ErrorCode =
  | "consent_required"
  | "gpu_busy"
  | "generation_in_progress"
  | "index_unavailable"
  | "not_a_pdf"
  | "upload_too_large"
  | "too_many_pages"
  | "validation_failed"
  | "unsupported_operation"
  | "provider_unreachable"
  | "not_found"
  | "internal";

export interface Problem {
  type: string;
  title: string;
  status: number;
  code: ErrorCode;
  detail: string;
  request_id?: string;
}

export interface Source {
  rank: number;
  doc_id: string;
  filename: string;
  page: number | null;
  preview: string;
  score: number | null;
  cited: boolean;
  supported: boolean | null;
  bbox?: [number, number, number, number];
}

export type GroundingStatus =
  | "grounded"
  | "partial"
  | "unsupported"
  | "rank_only"
  | "abstained"
  | "unverified";

export interface SentenceSupport {
  text: string;
  supported: boolean;
  score: number;
  cited_ranks: number[];
}

export interface Grounding {
  status: GroundingStatus;
  caption: string;
  citations: number[];
  uncited_claim_count: number;
  incomplete_context: boolean;
  truncation_warning: boolean;
  request_id: string;
  scope: { type: "all" | "documents"; doc_ids: string[] };
  sentence_support?: SentenceSupport[];
  injection_flags?: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  grounding?: Grounding;
  sources?: Source[];
  usage?: { ttft_ms: number; tokens: number; duration_ms: number };
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  scope: { type: "all" | "documents"; doc_ids: string[] };
  updated_at: string;
  messages?: ChatMessage[];
}

export type SummaryProfile =
  | "overview"
  | "detailed"
  | "study_notes"
  | "tables_figures"
  | "findings";

export type SummaryLength = "concise" | "standard" | "detailed";

export interface SummaryResponse {
  doc_id: string;
  profile: string;
  summary: string;
  model_version: string;
  cached: boolean;
  job_id?: string | null;
}

export interface SearchResult {
  query: string;
  sources: Source[];
  explanations?: {
    chunk_id: string;
    doc_id: string;
    dense_rank?: number | null;
    dense_score?: number | null;
    fts_rank?: number | null;
    fts_score?: number | null;
    rrf_score: number;
  }[];
}

export interface EmbeddingPoint {
  chunk_id: string;
  doc_id: string;
  filename: string;
  point: [number, number, number];
  page?: number | null;
  preview: string;
}

export interface ConstellationData {
  points: EmbeddingPoint[];
  dims: number;
  total_points: number;
}
