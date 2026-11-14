import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import {
  MOCK_DOCUMENTS,
  MOCK_HEALTH,
  MOCK_JOBS,
  MOCK_SESSIONS,
  MOCK_SETTINGS,
  MOCK_TELEMETRY,
} from "./mocks";
import {
  AppSettings,
  ChatSession,
  ConstellationData,
  DocumentDetail,
  DocumentSummary,
  Health,
  Job,
  SummaryResponse,
  Telemetry,
} from "./types";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export function useHealth() {
  return useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => (USE_MOCKS ? Promise.resolve(MOCK_HEALTH) : apiClient<Health>("/health")),
    refetchInterval: 10000,
  });
}

export function useTelemetry() {
  return useQuery<Telemetry>({
    queryKey: ["telemetry"],
    queryFn: () => (USE_MOCKS ? Promise.resolve(MOCK_TELEMETRY) : apiClient<Telemetry>("/telemetry")),
    refetchInterval: 3000,
  });
}

export function useSettings() {
  return useQuery<AppSettings>({
    queryKey: ["settings"],
    queryFn: () => (USE_MOCKS ? Promise.resolve(MOCK_SETTINGS) : apiClient<AppSettings>("/settings")),
  });
}

export function useUpdateCloudSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      enabled: boolean;
      provider: string;
      model: string;
      consent: boolean;
      api_key?: string;
    }) =>
      apiClient<AppSettings>("/settings/cloud", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });
}

export function useRevokeCloudCredentials() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient<AppSettings>("/settings/cloud/credentials", {
        method: "DELETE",
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });
}

export function useDocuments() {
  return useQuery<DocumentSummary[]>({
    queryKey: ["documents"],
    queryFn: () =>
      USE_MOCKS ? Promise.resolve(MOCK_DOCUMENTS) : apiClient<DocumentSummary[]>("/documents"),
    refetchInterval: 5000,
  });
}

export function useDocument(docId: string | null) {
  return useQuery<DocumentDetail>({
    queryKey: ["documents", docId],
    queryFn: () => apiClient<DocumentDetail>(`/documents/${docId}`),
    enabled: Boolean(docId),
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) =>
      apiClient<{ deleted: boolean }>(`/documents/${docId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function usePurgeDocuments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient<{ purged: boolean }>("/documents?confirm=PURGE", {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["chat_sessions"] });
    },
  });
}

export function useJobs() {
  return useQuery<Job[]>({
    queryKey: ["jobs"],
    queryFn: () => (USE_MOCKS ? Promise.resolve(MOCK_JOBS) : apiClient<Job[]>("/jobs")),
    refetchInterval: 2000,
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      apiClient<{ cancelled: boolean }>(`/jobs/${jobId}/cancel`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useChatSessions() {
  return useQuery<ChatSession[]>({
    queryKey: ["chat_sessions"],
    queryFn: () =>
      USE_MOCKS ? Promise.resolve(MOCK_SESSIONS) : apiClient<ChatSession[]>("/chat/sessions"),
  });
}

export function useChatSession(sessionId: string | null) {
  return useQuery<ChatSession>({
    queryKey: ["chat_sessions", sessionId],
    queryFn: () => {
      if (USE_MOCKS) {
        const found = MOCK_SESSIONS.find((s) => s.id === sessionId);
        return found ? Promise.resolve(found) : Promise.reject(new Error("Not found"));
      }
      return apiClient<ChatSession>(`/chat/sessions/${sessionId}`);
    },
    enabled: Boolean(sessionId),
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; scope?: { type: string; doc_ids: string[] } }) =>
      apiClient<ChatSession>("/chat/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat_sessions"] });
    },
  });
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiClient<{ deleted: boolean }>(`/chat/sessions/${sessionId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat_sessions"] });
    },
  });
}

export function useSummary(docId: string | null, profile: string, length: string = "standard") {
  return useQuery<SummaryResponse>({
    queryKey: ["summary", docId, profile, length],
    queryFn: () =>
      apiClient<SummaryResponse>(
        `/summaries?doc_id=${encodeURIComponent(docId!)}&profile=${profile}&length=${length}`
      ),
    enabled: Boolean(docId),
    retry: false,
  });
}

export function useConstellation(docIds?: string[]) {
  return useQuery<ConstellationData>({
    queryKey: ["constellation", docIds],
    queryFn: () => {
      const qs = docIds?.length ? `?doc_ids=${docIds.join(",")}` : "";
      return apiClient<ConstellationData>(`/visualize/embeddings${qs}`);
    },
  });
}
