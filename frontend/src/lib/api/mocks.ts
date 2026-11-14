import {
  AppSettings,
  ChatSession,
  ConstellationData,
  DocumentSummary,
  Health,
  Job,
  SummaryResponse,
  Telemetry,
} from "./types";

export const MOCK_HEALTH: Health = {
  status: "healthy",
  message: "Engine ready",
  ready: true,
  mode: "local",
  provider: "local",
  model: "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
  capabilities: {
    context_window: 16384,
    supports_vision: false,
    supports_streaming: true,
  },
  runtime: {
    llama_server_version: "b3600",
    build: "v2.0.0-rc1",
  },
};

export const MOCK_TELEMETRY: Telemetry = {
  gpu: { total_mb: 4096, used_mb: 1820, free_mb: 2276 },
  process: { rss_mb: 420.5, vms_mb: 1250.0 },
  inference: { busy: false },
  ts: new Date().toISOString(),
};

export const MOCK_SETTINGS: AppSettings = {
  mode: "local",
  egress_policy: "local",
  limits: {
    max_file_mb: 50,
    max_pages: 500,
    max_chat_turns: 50,
  },
  cloud: {
    enabled: false,
    provider: "groq",
    model: "groq/llama-3.3-70b-versatile",
    consented: false,
    has_key: false,
  },
};

export const MOCK_DOCUMENTS: DocumentSummary[] = [
  {
    doc_id: "doc_annual_report",
    filename: "Annual_Report_2025.pdf",
    sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    status: "indexed",
    pages: 42,
    chunks: 128,
    evidence_elements: 14,
    size_bytes: 4194304,
    created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
    has_vectors: true,
  },
  {
    doc_id: "doc_ml_paper",
    filename: "Attention_Is_All_You_Need.pdf",
    sha256: "f1d2d2f924e986ac86fdf7b36c94bcdf32beec15defc79e6027a42b1cf56b823",
    status: "indexed",
    pages: 15,
    chunks: 56,
    evidence_elements: 5,
    size_bytes: 1843200,
    created_at: new Date(Date.now() - 86400000).toISOString(),
    has_vectors: true,
  },
];

export const MOCK_JOBS: Job[] = [];

export const MOCK_SESSIONS: ChatSession[] = [
  {
    id: "session_welcome",
    title: "Document Ingestion & Overview",
    scope: { type: "all", doc_ids: [] },
    updated_at: new Date().toISOString(),
    messages: [
      {
        id: "msg_user_1",
        role: "user",
        content: "What are the primary findings in the annual report?",
        created_at: new Date(Date.now() - 3600000).toISOString(),
      },
      {
        id: "msg_asst_1",
        role: "assistant",
        content:
          "The company experienced a 24% increase in operating revenue [E1], driven primarily by growth in software subscriptions and cloud services [E2]. Operating margins remained healthy at 18.5% despite macroeconomic volatility [E1].",
        grounding: {
          status: "grounded",
          caption: "Answer fully supported by verified citations.",
          citations: [1, 2],
          uncited_claim_count: 0,
          incomplete_context: false,
          truncation_warning: false,
          request_id: "req_demo_01",
          scope: { type: "all", doc_ids: [] },
          sentence_support: [
            {
              text: "The company experienced a 24% increase in operating revenue [E1], driven primarily by growth in software subscriptions and cloud services [E2].",
              supported: true,
              score: 0.94,
              cited_ranks: [1, 2],
            },
            {
              text: "Operating margins remained healthy at 18.5% despite macroeconomic volatility [E1].",
              supported: true,
              score: 0.89,
              cited_ranks: [1],
            },
          ],
        },
        sources: [
          {
            rank: 1,
            doc_id: "doc_annual_report",
            filename: "Annual_Report_2025.pdf",
            page: 4,
            preview:
              "Total operating revenue reached $142.8M, representing a 24% year-over-year increase. Operating margin settled at 18.5%.",
            score: 0.88,
            cited: true,
            supported: true,
          },
          {
            rank: 2,
            doc_id: "doc_annual_report",
            filename: "Annual_Report_2025.pdf",
            page: 12,
            preview:
              "Subscription ARR surged 38% while enterprise cloud tier adoption grew across all customer segments.",
            score: 0.82,
            cited: true,
            supported: true,
          },
        ],
        usage: { ttft_ms: 245.0, tokens: 42, duration_ms: 1120.0 },
        created_at: new Date(Date.now() - 3590000).toISOString(),
      },
    ],
  },
];

export async function streamMockMessage(
  onEvent: (event: string, data: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const steps = [
    { event: "status", data: { phase: "retrieving" }, delay: 200 },
    {
      event: "meta",
      data: {
        request_id: "req_mock_stream",
        mode: "qa",
        scope: { type: "all", doc_ids: [] },
        sources: MOCK_SESSIONS[0].messages![1].sources,
      },
      delay: 300,
    },
    { event: "status", data: { phase: "generating" }, delay: 200 },
    { event: "token", data: { t: "The " }, delay: 60 },
    { event: "token", data: { t: "key " }, delay: 60 },
    { event: "token", data: { t: "findings " }, delay: 60 },
    { event: "token", data: { t: "indicate " }, delay: 60 },
    { event: "token", data: { t: "robust " }, delay: 60 },
    { event: "token", data: { t: "growth " }, delay: 60 },
    { event: "token", data: { t: "[E1] " }, delay: 60 },
    { event: "token", data: { t: "in " }, delay: 60 },
    { event: "token", data: { t: "cloud " }, delay: 60 },
    { event: "token", data: { t: "services " }, delay: 60 },
    { event: "token", data: { t: "[E2]." }, delay: 60 },
    { event: "status", data: { phase: "verifying" }, delay: 300 },
    {
      event: "final",
      data: {
        message_id: "msg_mock_final",
        answer_markdown:
          "The key findings indicate robust growth [E1] in cloud services [E2].",
        grounding: MOCK_SESSIONS[0].messages![1].grounding,
        sources: MOCK_SESSIONS[0].messages![1].sources,
        usage: { ttft_ms: 180, tokens: 16, duration_ms: 850 },
      },
      delay: 100,
    },
  ];

  for (const step of steps) {
    if (signal?.aborted) break;
    await new Promise((r) => setTimeout(r, step.delay));
    if (signal?.aborted) break;
    onEvent(step.event, step.data);
  }
}
