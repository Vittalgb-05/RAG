"use client";

import React, { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  Upload,
  RefreshCw,
  Trash2,
  MessageSquare,
  Sparkles,
  Search,
  AlertOctagon,
  Eye,
  CheckCircle2,
  Clock,
  XCircle,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  useDeleteDocument,
  useDocument,
  useDocuments,
  usePurgeDocuments,
} from "@/lib/api/queries";
import { apiClient } from "@/lib/api/client";
import { CountUp } from "@/components/motion/count-up";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { DocumentSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export default function LibraryPage() {
  const router = useRouter();
  const { data: documents = [], refetch: refetchDocs } = useDocuments();
  const deleteMutation = useDeleteDocument();
  const purgeMutation = usePurgeDocuments();

  const [searchQuery, setSearchQuery] = useState("");
  const [inspectDocId, setInspectDocId] = useState<string | null>(null);
  const [purgeModalOpen, setPurgeModalOpen] = useState(false);
  const [purgeConfirmText, setPurgeConfirmText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: inspectedDoc } = useDocument(inspectDocId);

  // Stats calculation
  const totalDocs = documents.length;
  const totalPages = documents.reduce((sum, d) => sum + (d.pages || 0), 0);
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunks || 0), 0);
  const indexedCount = documents.filter((d) => d.status === "indexed").length;
  const indexedPct = totalDocs > 0 ? Math.round((indexedCount / totalDocs) * 100) : 100;

  const filteredDocs = documents.filter((d) =>
    d.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleUploadFiles = async (files: FileList | null) => {
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
      toast.success("Document(s) queued for ingestion");
      refetchDocs();
    } catch (err: any) {
      toast.error(err.message || "Upload failed");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleReindex = async (docId: string) => {
    try {
      toast.info(`Starting re-index for document...`);
      await apiClient(`/documents/${docId}/reindex`, { method: "POST" });
      toast.success("Re-indexing job queued");
    } catch (err: any) {
      toast.error(err.message || "Re-indexing failed");
    }
  };

  const handlePurge = () => {
    if (purgeConfirmText !== "PURGE") {
      toast.error("Type PURGE exactly to confirm library deletion");
      return;
    }
    purgeMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success("Library purged completely");
        setPurgeModalOpen(false);
        setPurgeConfirmText("");
      },
      onError: (err: any) => {
        toast.error(err.message || "Purge failed");
      },
    });
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        handleUploadFiles(e.dataTransfer.files);
      }}
      className="p-8 max-w-7xl mx-auto space-y-8 relative min-h-full"
    >
      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => handleUploadFiles(e.target.files)}
        multiple
        accept=".pdf"
        className="hidden"
      />

      {/* Drag Overlay */}
      {isDragging && (
        <div className="fixed inset-0 z-50 bg-[#050507]/80 backdrop-blur-md border-4 border-dashed border-[#A78BFA] flex items-center justify-center p-8">
          <div className="text-center space-y-3">
            <Upload className="w-12 h-12 text-[#A78BFA] mx-auto animate-bounce" />
            <h3 className="text-xl font-bold text-[#F4F4F5]">Drop PDF files to upload</h3>
            <p className="text-xs text-[#A1A1AA]">Automatic OCR and multimodal extraction</p>
          </div>
        </div>
      )}

      {/* Header Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SpotlightCard className="p-4">
          <p className="text-xs text-[#A1A1AA] uppercase tracking-wider font-semibold">
            Documents
          </p>
          <p className="text-2xl font-bold text-[#F4F4F5] mt-1">
            <CountUp to={totalDocs} />
          </p>
        </SpotlightCard>
        <SpotlightCard className="p-4">
          <p className="text-xs text-[#A1A1AA] uppercase tracking-wider font-semibold">
            Total Pages
          </p>
          <p className="text-2xl font-bold text-[#22D3EE] mt-1">
            <CountUp to={totalPages} />
          </p>
        </SpotlightCard>
        <SpotlightCard className="p-4">
          <p className="text-xs text-[#A1A1AA] uppercase tracking-wider font-semibold">
            Total Chunks
          </p>
          <p className="text-2xl font-bold text-[#A78BFA] mt-1">
            <CountUp to={totalChunks} />
          </p>
        </SpotlightCard>
        <SpotlightCard className="p-4">
          <p className="text-xs text-[#A1A1AA] uppercase tracking-wider font-semibold">
            Indexed Health
          </p>
          <p className="text-2xl font-bold text-[#34D399] mt-1">
            <CountUp to={indexedPct} suffix="%" />
          </p>
        </SpotlightCard>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-[#71717A] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search documents by name..."
            className="w-full pl-9 pr-4 py-2 rounded-[10px] bg-[#0C0C11] border border-[rgba(255,255,255,0.08)] text-sm text-[#F4F4F5] placeholder-[#71717A] outline-none focus:border-[#A78BFA]/50 transition-colors"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 rounded-[10px] bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black text-xs font-semibold hover:opacity-90 transition-opacity shadow-[0_0_15px_rgba(167,139,250,0.25)]"
          >
            <Upload className="w-4 h-4" />
            <span>Upload PDF</span>
          </button>

          <button
            onClick={() => setPurgeModalOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-[#F87171]/10 border border-[#F87171]/20 text-[#F87171] text-xs font-semibold hover:bg-[#F87171]/20 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            <span>Purge All</span>
          </button>
        </div>
      </div>

      {/* Document Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredDocs.map((doc: DocumentSummary) => {
          const isFailed = doc.status === "failed";
          const isIndexing = doc.status === "indexing";

          return (
            <SpotlightCard key={doc.doc_id} className="flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 truncate">
                    <FileText className="w-5 h-5 text-[#A78BFA] shrink-0" />
                    <span className="font-semibold text-sm text-[#F4F4F5] truncate" title={doc.filename}>
                      {doc.filename}
                    </span>
                  </div>

                  {/* Status chip */}
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider shrink-0 flex items-center gap-1",
                      isFailed
                        ? "bg-[#F87171]/10 text-[#F87171] border border-[#F87171]/20"
                        : isIndexing
                        ? "bg-[#FBBF24]/10 text-[#FBBF24] border border-[#FBBF24]/20 animate-pulse"
                        : "bg-[#34D399]/10 text-[#34D399] border border-[#34D399]/20"
                    )}
                  >
                    {isFailed ? (
                      <XCircle className="w-3 h-3" />
                    ) : isIndexing ? (
                      <Clock className="w-3 h-3" />
                    ) : (
                      <CheckCircle2 className="w-3 h-3" />
                    )}
                    {doc.status}
                  </span>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[#A1A1AA]">
                  <div>
                    Pages: <span className="text-[#F4F4F5] font-medium">{doc.pages}</span>
                  </div>
                  <div>
                    Chunks: <span className="text-[#F4F4F5] font-medium">{doc.chunks}</span>
                  </div>
                  <div>
                    Visual: <span className="text-[#F4F4F5] font-medium">{doc.evidence_elements}</span>
                  </div>
                  <div>
                    Size:{" "}
                    <span className="text-[#F4F4F5] font-medium">
                      {(doc.size_bytes / (1024 * 1024)).toFixed(1)} MB
                    </span>
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-[rgba(255,255,255,0.06)]">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => router.push(`/chat?doc=${doc.doc_id}`)}
                    className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                    title="Chat about this document"
                  >
                    <MessageSquare className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => router.push(`/summarizer?doc=${doc.doc_id}`)}
                    className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                    title="Summarize document"
                  >
                    <Sparkles className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setInspectDocId(doc.doc_id)}
                    className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                    title="Inspect chunks and evidence"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleReindex(doc.doc_id)}
                    className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#22D3EE] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                    title={isFailed ? "Repair vectors" : "Re-index"}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(doc.doc_id)}
                    className="p-1.5 rounded-lg text-[#71717A] hover:text-[#F87171] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                    title="Delete document"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </SpotlightCard>
          );
        })}
      </div>

      {/* Inspect Side Sheet */}
      {inspectDocId && inspectedDoc && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs">
          <div className="w-full max-w-xl bg-[#0C0C11] border-l border-[rgba(255,255,255,0.12)] p-6 overflow-y-auto space-y-6">
            <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.08)] pb-4">
              <h3 className="font-semibold text-[#F4F4F5] text-base truncate pr-4">
                {inspectedDoc.filename}
              </h3>
              <button
                onClick={() => setInspectDocId(null)}
                className="text-[#71717A] hover:text-[#F4F4F5] p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-[#A1A1AA]">
                Chunks ({inspectedDoc.chunks.length})
              </h4>
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {inspectedDoc.chunks.map((chk: any, i: number) => (
                  <div
                    key={i}
                    className="p-3 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.06)] text-xs text-[#F4F4F5] space-y-1"
                  >
                    <div className="flex justify-between text-[10px] text-[#A78BFA] font-mono">
                      <span>Chunk #{i + 1}</span>
                      <span>Page {chk.page}</span>
                    </div>
                    <p className="line-clamp-3">{chk.content}</p>
                  </div>
                ))}
              </div>

              {inspectedDoc.evidence.length > 0 && (
                <>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-[#A1A1AA] pt-4">
                    Visual Evidence ({inspectedDoc.evidence.length})
                  </h4>
                  <div className="space-y-3">
                    {inspectedDoc.evidence.map((ev: any, i: number) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.06)] text-xs space-y-1"
                      >
                        <div className="text-[10px] text-[#22D3EE] font-mono capitalize">
                          {ev.kind} on Page {ev.page}
                        </div>
                        <p className="text-[#F4F4F5]">{ev.content}</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Purge Modal */}
      {purgeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-[14px] bg-[#14141B] border border-[#F87171]/40 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-[#F87171]">
              <AlertOctagon className="w-6 h-6 shrink-0" />
              <h3 className="font-bold text-base text-[#F4F4F5]">Purge Entire Library</h3>
            </div>
            <p className="text-xs text-[#A1A1AA] leading-relaxed">
              This will permanently delete all indexed PDF documents, LanceDB vector tables, disk caches, and chat history. To confirm, type <span className="font-mono text-[#F87171] font-bold">PURGE</span> below:
            </p>

            <input
              type="text"
              value={purgeConfirmText}
              onChange={(e) => setPurgeConfirmText(e.target.value)}
              placeholder="Type PURGE to confirm"
              className="w-full px-3 py-2 rounded-lg bg-[#0C0C11] border border-[rgba(255,255,255,0.1)] text-sm text-[#F4F4F5] outline-none focus:border-[#F87171]"
            />

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => {
                  setPurgeModalOpen(false);
                  setPurgeConfirmText("");
                }}
                className="px-4 py-2 rounded-lg text-xs text-[#A1A1AA] hover:text-[#F4F4F5]"
              >
                Cancel
              </button>
              <button
                onClick={handlePurge}
                disabled={purgeConfirmText !== "PURGE" || purgeMutation.isPending}
                className="px-4 py-2 rounded-lg bg-[#F87171] text-black font-semibold text-xs hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
              >
                Confirm Purge
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
