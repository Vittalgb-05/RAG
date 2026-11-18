import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
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

export function useHealth() {
  return useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => apiClient<Health>("/health"),
    refetchInterval: 10000,
  });
}

export function useTelemetry() {
  return useQuery<Telemetry>({
    queryKey: ["telemetry"],
    queryFn: () => apiClient<Telemetry>("/telemetry"),
    refetchInterval: 3000,
  });
}

export function useSettings() {
  return useQuery<AppSettings>({
    queryKey: ["settings"],
    queryFn: () => apiClient<AppSettings>("/settings"),
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
    queryFn: () => apiClient<DocumentSummary[]>("/documents"),
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
    queryFn: () => apiClient<Job[]>("/jobs"),
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
    queryFn: () => apiClient<ChatSession[]>("/chat/sessions"),
  });
}

export function useChatSession(sessionId: string | null) {
  return useQuery<ChatSession>({
    queryKey: ["chat_sessions", sessionId],
    queryFn: () => apiClient<ChatSession>(`/chat/sessions/${sessionId}`),
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

export function useUpdateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title, scope }: { id: string; title?: string; scope?: { type: string; doc_ids: string[] } }) =>
      apiClient<ChatSession>(`/chat/sessions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title, scope }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat_sessions"] });
      queryClient.invalidateQueries({ queryKey: ["chat_session"] });
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

export function usePrivacyLedger() {
  return useQuery<{ entries: any[] }>({
    queryKey: ["privacy", "ledger"],
    queryFn: () => apiClient<{ entries: any[] }>("/privacy/ledger"),
    refetchInterval: 10000,
  });
}
