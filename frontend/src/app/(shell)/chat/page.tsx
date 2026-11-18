"use client";

import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
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
  Download,
  Layers,
  Mic,
  MicOff,
  ChevronDown,
  Check,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import {
  useChatSession,
  useChatSessions,
  useCreateChatSession,
  useDeleteChatSession,
  useUpdateChatSession,
  useDocuments,
} from "@/lib/api/queries";
import { streamSSE } from "@/lib/api/sse";
import { apiClient } from "@/lib/api/client";
import { ChatMessage, Source } from "@/lib/api/types";
import { MessageBubble } from "@/components/chat/message-bubble";
import { RetrievalXRayDrawer } from "@/components/chat/retrieval-xray-drawer";
import { BlurText } from "@/components/motion/blur-text";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { Magnet } from "@/components/motion/magnet";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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
  const updateSessionMutation = useUpdateChatSession();
  const { data: documents = [] } = useDocuments();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { data: activeSession, refetch: refetchActiveSession } = useChatSession(activeSessionId);

  // Session inline rename
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Scope state
  const [scopeType, setScopeType] = useState<"all" | "selected">("all");
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [showDocSelector, setShowDocSelector] = useState(false);

  // X-Ray Drawer
  const [isXRayOpen, setIsXRayOpen] = useState(false);
  const [xrayQuery, setXrayQuery] = useState("");

  // Voice dictation
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Streaming state
  const [inputPrompt, setInputPrompt] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamingTokens, setStreamingTokens] = useState<string>("");
  const [streamSources, setStreamSources] = useState<Source[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize or synchronize scope with active session or query param
  useEffect(() => {
    if (activeSession?.scope) {
      if (activeSession.scope.type === "documents") {
        setScopeType("selected");
        setSelectedDocIds(activeSession.scope.doc_ids || []);
      } else {
        setScopeType("all");
      }
    } else if (docParam) {
      setScopeType("selected");
      setSelectedDocIds([docParam]);
    }
  }, [activeSession, docParam]);

  // Set default active session or select first
  useEffect(() => {
    if (sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages, streamingTokens]);

  // Sync latest query for X-Ray
  useEffect(() => {
    if (activeSession?.messages && activeSession.messages.length > 0) {
      const userMsgs = activeSession.messages.filter((m) => m.role === "user");
      if (userMsgs.length > 0) {
        setXrayQuery(userMsgs[userMsgs.length - 1].content);
      }
    }
  }, [activeSession?.messages]);

  const handleNewChat = () => {
    const scope =
      scopeType === "selected"
        ? { type: "documents" as const, doc_ids: selectedDocIds }
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

  const handleSaveTitle = (sessionId: string) => {
    if (!editingTitle.trim()) {
      setEditingSessionId(null);
      return;
    }
    updateSessionMutation.mutate(
      { id: sessionId, title: editingTitle.trim() },
      {
        onSuccess: () => {
          setEditingSessionId(null);
        },
      }
    );
  };

  const handleScopeChange = (type: "all" | "selected") => {
    setScopeType(type);
    if (type === "all") {
      setShowDocSelector(false);
    } else {
      setShowDocSelector(true);
    }

    if (activeSessionId) {
      const newScope =
        type === "selected"
          ? { type: "documents" as const, doc_ids: selectedDocIds }
          : { type: "all" as const, doc_ids: [] };
      updateSessionMutation.mutate({ id: activeSessionId, scope: newScope });
    }
  };

  const toggleDocInScope = (docId: string) => {
    const updated = selectedDocIds.includes(docId)
      ? selectedDocIds.filter((id) => id !== docId)
      : [...selectedDocIds, docId];
    setSelectedDocIds(updated);

    if (activeSessionId && scopeType === "selected") {
      updateSessionMutation.mutate({
        id: activeSessionId,
        scope: { type: "documents" as const, doc_ids: updated },
      });
    }
  };

  const handleExportChat = async () => {
    if (!activeSessionId) return;
    try {
      const res = await fetch(`${API_URL.replace(/\/$/, "")}/api/v1/chat/sessions/${activeSessionId}/export?format=md`);
      if (!res.ok) throw new Error("Failed to export chat");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `chat-${activeSessionId}.md`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Chat exported to markdown");
    } catch (err: any) {
      toast.error(err.message || "Failed to export chat");
    }
  };

  const toggleDictation = () => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.error("Speech recognition is not supported in this browser.");
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setIsListening(true);
        toast.info("Listening... Speak now");
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setInputPrompt((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognition.onerror = (event: any) => {
        setIsListening(false);
        toast.error(`Dictation error: ${event.error || "unknown"}`);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setIsListening(false);
      toast.error("Could not start speech recognition");
    }
  };

  const handleStop = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (activeSessionId) {
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
    const scopeObj =
      scopeType === "selected"
        ? { type: "documents" as const, doc_ids: selectedDocIds }
        : { type: "all" as const, doc_ids: [] };

    if (!targetSessionId) {
      const newSession = await createSessionMutation.mutateAsync({
        title: promptToSend.slice(0, 32),
        scope: scopeObj,
      });
      targetSessionId = newSession.id;
      setActiveSessionId(targetSessionId);
    }

    setXrayQuery(promptToSend);
    setInputPrompt("");
    setIsStreaming(true);
    setCurrentPhase("retrieving");
    setStreamingTokens("");
    setStreamSources([]);

    abortControllerRef.current = new AbortController();

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
              {editingSessionId === s.id ? (
                <input
                  type="text"
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onBlur={() => handleSaveTitle(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveTitle(s.id);
                    if (e.key === "Escape") setEditingSessionId(null);
                  }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                  className="bg-transparent text-[#F4F4F5] border-b border-[#A78BFA] outline-none text-xs w-full mr-2"
                />
              ) : (
                <span
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEditingSessionId(s.id);
                    setEditingTitle(s.title || "Untitled Chat");
                  }}
                  className="truncate flex-1 mr-2 select-none"
                  title="Double-click to rename"
                >
                  {s.title || "Untitled Chat"}
                </span>
              )}
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
        {/* Chat Header with Scope Bar, X-Ray, and Export */}
        <div className="h-14 border-b border-[rgba(255,255,255,0.08)] bg-[#0C0C11]/80 backdrop-blur-md px-6 flex items-center justify-between shrink-0">
          {/* Scope Segmented Control */}
          <div className="flex items-center gap-3">
            <div className="flex items-center bg-[#14141B] p-0.5 rounded-lg border border-[rgba(255,255,255,0.08)] relative">
              <button
                onClick={() => handleScopeChange("all")}
                className={cn(
                  "relative z-10 px-3 py-1 text-xs font-medium rounded-md transition-colors",
                  scopeType === "all" ? "text-[#F4F4F5]" : "text-[#71717A] hover:text-[#A1A1AA]"
                )}
              >
                All documents
                {scopeType === "all" && (
                  <motion.div
                    layoutId="scopeIndicator"
                    className="absolute inset-0 bg-[#A78BFA]/20 border border-[#A78BFA]/30 rounded-md -z-10"
                    transition={{ type: "spring", stiffness: 260, damping: 26 }}
                  />
                )}
              </button>

              <button
                onClick={() => handleScopeChange("selected")}
                className={cn(
                  "relative z-10 px-3 py-1 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5",
                  scopeType === "selected"
                    ? "text-[#F4F4F5]"
                    : "text-[#71717A] hover:text-[#A1A1AA]"
                )}
              >
                <span>Selected</span>
                {selectedDocIds.length > 0 && (
                  <span className="w-4 h-4 rounded-full bg-[#A78BFA] text-black text-[10px] font-bold flex items-center justify-center">
                    {selectedDocIds.length}
                  </span>
                )}
                {scopeType === "selected" && (
                  <motion.div
                    layoutId="scopeIndicator"
                    className="absolute inset-0 bg-[#A78BFA]/20 border border-[#A78BFA]/30 rounded-md -z-10"
                    transition={{ type: "spring", stiffness: 260, damping: 26 }}
                  />
                )}
              </button>
            </div>

            {/* Document Multi-select Trigger when Selected is active */}
            {scopeType === "selected" && (
              <div className="relative">
                <button
                  onClick={() => setShowDocSelector(!showDocSelector)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#A1A1AA] hover:text-[#F4F4F5] transition-colors"
                >
                  <FileText className="w-3.5 h-3.5 text-[#22D3EE]" />
                  <span>
                    {selectedDocIds.length === 0
                      ? "Choose documents..."
                      : `${selectedDocIds.length} chosen`}
                  </span>
                  <ChevronDown className="w-3 h-3 ml-0.5" />
                </button>

                {/* Dropdown Popover */}
                <AnimatePresence>
                  {showDocSelector && (
                    <motion.div
                      initial={{ opacity: 0, y: 4, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 4, scale: 0.98 }}
                      className="absolute left-0 mt-1 w-64 max-h-60 overflow-y-auto p-1.5 rounded-xl bg-[#0C0C11] border border-[rgba(255,255,255,0.12)] shadow-2xl z-50 space-y-1"
                    >
                      {documents.length === 0 ? (
                        <div className="p-3 text-[11px] text-[#71717A] text-center">
                          No documents available in library.
                        </div>
                      ) : (
                        documents.map((d) => {
                          const isSelected = selectedDocIds.includes(d.doc_id);
                          return (
                            <div
                              key={d.doc_id}
                              onClick={() => toggleDocInScope(d.doc_id)}
                              className={cn(
                                "flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition-colors",
                                isSelected
                                  ? "bg-[#A78BFA]/15 text-[#F4F4F5]"
                                  : "text-[#A1A1AA] hover:bg-[rgba(255,255,255,0.04)] hover:text-[#F4F4F5]"
                              )}
                            >
                              <span className="truncate mr-2">{d.filename}</span>
                              {isSelected && <Check className="w-3.5 h-3.5 text-[#A78BFA] shrink-0" />}
                            </div>
                          );
                        })
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>

          {/* Action Bar: Retrieval X-Ray & Export */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (!xrayQuery) {
                  toast.info("Submit a question first to inspect retrieval reasoning");
                }
                setIsXRayOpen(true);
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#A1A1AA] hover:text-[#22D3EE] hover:border-[#22D3EE]/30 transition-colors shadow-sm"
              title="Inspect dense vs sparse vs fused retrieval rankings"
            >
              <Layers className="w-3.5 h-3.5 text-[#22D3EE]" />
              <span>Retrieval X-Ray</span>
            </button>

            {activeSessionId && (
              <button
                onClick={handleExportChat}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors shadow-sm"
                title="Export conversation as markdown"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export</span>
              </button>
            )}
          </div>
        </div>

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

            {/* Web Speech Dictation */}
            <button
              onClick={toggleDictation}
              className={cn(
                "p-2 rounded-lg transition-all",
                isListening
                  ? "bg-[#F472B6]/20 text-[#F472B6] border border-[#F472B6]/40 animate-pulse"
                  : "text-[#71717A] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
              )}
              title={isListening ? "Listening... Click to stop" : "Voice dictation (Web Speech API)"}
            >
              {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
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

      {/* Retrieval X-Ray Drawer */}
      <RetrievalXRayDrawer
        isOpen={isXRayOpen}
        onClose={() => setIsXRayOpen(false)}
        query={xrayQuery || "What are the key findings?"}
      />
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
