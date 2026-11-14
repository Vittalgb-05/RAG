"use client";

import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Send,
  Square,
  Paperclip,
  Plus,
  Trash2,
  Sparkles,
  BookOpen,
  HelpCircle,
  FileSearch,
} from "lucide-react";
import { toast } from "sonner";
import {
  useChatSession,
  useChatSessions,
  useCreateChatSession,
  useDeleteChatSession,
  useDocuments,
} from "@/lib/api/queries";
import { streamSSE } from "@/lib/api/sse";
import { streamMockMessage } from "@/lib/api/mocks";
import { apiClient } from "@/lib/api/client";
import { ChatMessage, Source } from "@/lib/api/types";
import { MessageBubble } from "@/components/chat/message-bubble";
import { BlurText } from "@/components/motion/blur-text";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { Magnet } from "@/components/motion/magnet";
import { cn } from "@/lib/utils";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

const SUGGESTED_PROMPTS = [
  {
    icon: FileSearch,
    title: "Executive Summary",
    prompt: "Provide an executive summary of the uploaded document with key takeaways.",
  },
  {
    icon: BookOpen,
    title: "Key Methodologies",
    prompt: "What methodologies and technical architectures are described in this document?",
  },
  {
    icon: Sparkles,
    title: "Data & Findings",
    prompt: "Summarize the primary metrics, statistics, and findings reported.",
  },
  {
    icon: HelpCircle,
    title: "Verify Assumptions",
    prompt: "What limitations or critical assumptions does the author specify?",
  },
];

function ChatContent() {
  const searchParams = useSearchParams();
  const docParam = searchParams.get("doc");

  const { data: sessions = [], refetch: refetchSessions } = useChatSessions();
  const createSessionMutation = useCreateChatSession();
  const deleteSessionMutation = useDeleteChatSession();
  const { data: documents = [] } = useDocuments();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { data: activeSession, refetch: refetchActiveSession } = useChatSession(activeSessionId);

  // Streaming state
  const [inputPrompt, setInputPrompt] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamingTokens, setStreamingTokens] = useState<string>("");
  const [streamSources, setStreamSources] = useState<Source[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Set default active session or create initial
  useEffect(() => {
    if (sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages, streamingTokens]);

  const handleNewChat = () => {
    const scope = docParam
      ? { type: "documents" as const, doc_ids: [docParam] }
      : { type: "all" as const, doc_ids: [] };

    createSessionMutation.mutate(
      { title: "New Conversation", scope },
      {
        onSuccess: (newSession) => {
          setActiveSessionId(newSession.id);
        },
      }
    );
  };

  const handleStop = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (activeSessionId && !USE_MOCKS) {
      try {
        await apiClient(`/chat/sessions/${activeSessionId}/stop`, { method: "POST" });
      } catch {}
    }
    setIsStreaming(false);
    setCurrentPhase(null);
  };

  const handleSend = async (customPrompt?: string) => {
    const promptToSend = customPrompt || inputPrompt;
    if (!promptToSend.trim() || isStreaming) return;

    let targetSessionId = activeSessionId;
    if (!targetSessionId) {
      const scope = docParam
        ? { type: "documents" as const, doc_ids: [docParam] }
        : { type: "all" as const, doc_ids: [] };
      const newSession = await createSessionMutation.mutateAsync({
        title: promptToSend.slice(0, 32),
        scope,
      });
      targetSessionId = newSession.id;
      setActiveSessionId(targetSessionId);
    }

    setInputPrompt("");
    setIsStreaming(true);
    setCurrentPhase("retrieving");
    setStreamingTokens("");
    setStreamSources([]);

    abortControllerRef.current = new AbortController();

    const scopeObj = docParam
      ? { type: "documents" as const, doc_ids: [docParam] }
      : { type: "all" as const, doc_ids: [] };

    const onEvent = (event: string, data: any) => {
      if (event === "status") {
        setCurrentPhase(data.phase);
      } else if (event === "meta") {
        if (data.sources) setStreamSources(data.sources);
      } else if (event === "token") {
        setStreamingTokens((prev) => prev + (data.t || ""));
      } else if (event === "replace") {
        setStreamingTokens(data.answer_markdown || "");
      } else if (event === "final") {
        setIsStreaming(false);
        setCurrentPhase(null);
        setStreamingTokens("");
        refetchActiveSession();
        refetchSessions();
      } else if (event === "error") {
        setIsStreaming(false);
        setCurrentPhase(null);
        toast.error(data.detail || data.title || "Generation failed");
      }
    };

    if (USE_MOCKS) {
      streamMockMessage(onEvent, abortControllerRef.current.signal);
    } else {
      try {
        await streamSSE({
          url: `/chat/sessions/${targetSessionId}/messages/stream`,
          body: { content: promptToSend, scope: scopeObj },
          signal: abortControllerRef.current.signal,
          onEvent,
          onError: (err) => {
            setIsStreaming(false);
            setCurrentPhase(null);
            toast.error(err.message || "Streaming connection failed");
          },
        });
      } catch (err: any) {
        setIsStreaming(false);
        setCurrentPhase(null);
        toast.error(err.message || "Failed to start answer generation");
      }
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }

    try {
      toast.info(`Uploading ${files.length} document(s)...`);
      await apiClient("/documents", {
        method: "POST",
        body: formData,
      });
      toast.success("Document uploaded and ingestion started in background!");
    } catch (err: any) {
      toast.error(err.message || "Upload failed");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const messages = activeSession?.messages || [];

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Sessions Left Rail */}
      <div className="w-64 border-r border-[rgba(255,255,255,0.08)] bg-[#0C0C11] flex flex-col shrink-0">
        <div className="p-3 border-b border-[rgba(255,255,255,0.08)]">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black text-xs font-semibold hover:opacity-90 transition-opacity shadow-[0_0_15px_rgba(167,139,250,0.25)]"
          >
            <Plus className="w-4 h-4" />
            <span>New Chat</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => setActiveSessionId(s.id)}
              className={cn(
                "group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors",
                s.id === activeSessionId
                  ? "bg-[rgba(167,139,250,0.12)] border border-[rgba(167,139,250,0.25)] text-[#F4F4F5] font-medium"
                  : "text-[#A1A1AA] hover:bg-[rgba(255,255,255,0.04)] hover:text-[#F4F4F5]"
              )}
            >
              <span className="truncate flex-1 mr-2">{s.title || "Untitled Chat"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSessionMutation.mutate(s.id, {
                    onSuccess: () => {
                      if (activeSessionId === s.id) setActiveSessionId(null);
                    },
                  });
                }}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-[#F87171] transition-opacity"
                title="Delete session"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main Conversation Feed & Composer */}
      <div className="flex-1 flex flex-col h-full bg-[#050507] overflow-hidden">
        {/* Messages scroll area */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && !isStreaming ? (
            <div className="h-full flex flex-col items-center justify-center max-w-xl mx-auto text-center space-y-6 py-12">
              <BlurText
                text="Ask anything about your documents"
                className="text-2xl font-bold text-[#F4F4F5] tracking-tight"
              />
              <p className="text-xs text-[#A1A1AA] max-w-md">
                Grounded multimodal reasoning with verifiable citations. Select a suggested
                query below or upload a PDF to begin.
              </p>

              <div className="grid grid-cols-2 gap-3 w-full text-left">
                {SUGGESTED_PROMPTS.map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <SpotlightCard
                      key={idx}
                      onClick={() => handleSend(item.prompt)}
                      className="cursor-pointer hover:border-[#A78BFA]/40 transition-all p-4"
                    >
                      <Icon className="w-5 h-5 text-[#A78BFA] mb-2" />
                      <h4 className="text-xs font-semibold text-[#F4F4F5] mb-1">
                        {item.title}
                      </h4>
                      <p className="text-[11px] text-[#A1A1AA] line-clamp-2">
                        {item.prompt}
                      </p>
                    </SpotlightCard>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}

              {/* Live Streaming Bubble */}
              {isStreaming && (
                <div className="flex gap-3.5 my-4 max-w-3xl mr-auto flex-row">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-gradient-to-br from-[#A78BFA] to-[#22D3EE] text-black text-xs shadow-[0_0_12px_rgba(167,139,250,0.3)]">
                    <Sparkles className="w-4 h-4 animate-spin" />
                  </div>
                  <div className="flex flex-col flex-1">
                    <div className="p-4 rounded-[14px] bg-[#0C0C11] border border-[rgba(255,255,255,0.08)] text-sm text-[#F4F4F5] rounded-tl-none shadow-sm space-y-2">
                      {currentPhase && (
                        <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-[#A78BFA]/10 text-[#A78BFA] border border-[#A78BFA]/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#A78BFA] animate-ping" />
                          Phase: {currentPhase}
                        </div>
                      )}
                      <p className="whitespace-pre-wrap leading-relaxed">
                        {streamingTokens}
                        <span className="inline-block w-2 h-4 ml-0.5 bg-[#22D3EE] animate-pulse align-middle" />
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="p-4 border-t border-[rgba(255,255,255,0.08)] bg-[#0C0C11]/90 backdrop-blur-md">
          <div className="max-w-3xl mx-auto flex items-end gap-2 bg-[#14141B] border border-[rgba(255,255,255,0.1)] rounded-[14px] p-2 shadow-inner focus-within:border-[rgba(167,139,250,0.4)] transition-all">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".pdf"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-2 text-[#71717A] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] rounded-lg transition-colors"
              title="Attach PDF document"
            >
              <Paperclip className="w-4 h-4" />
            </button>

            <textarea
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask a question about your documents... (Enter to send, Shift+Enter for newline)"
              rows={1}
              className="flex-1 bg-transparent text-sm text-[#F4F4F5] placeholder-[#71717A] outline-none resize-none max-h-32 py-1.5 px-2"
            />

            {isStreaming ? (
              <button
                onClick={handleStop}
                className="p-2 rounded-lg bg-[#F87171] text-black hover:opacity-90 transition-opacity"
                title="Stop generation"
              >
                <Square className="w-4 h-4 fill-current" />
              </button>
            ) : (
              <Magnet strength={10}>
                <button
                  onClick={() => handleSend()}
                  disabled={!inputPrompt.trim()}
                  className="p-2 rounded-lg bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-[0_0_12px_rgba(167,139,250,0.3)]"
                  title="Send message"
                >
                  <Send className="w-4 h-4" />
                </button>
              </Magnet>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex h-full items-center justify-center text-xs text-[#71717A]">
          Loading chat...
        </div>
      }
    >
      <ChatContent />
    </React.Suspense>
  );
}
