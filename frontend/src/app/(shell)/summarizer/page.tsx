"use client";

import React, { useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import {
  Sparkles,
  FileText,
  Copy,
  Download,
  Check,
  RefreshCw,
  BookOpen,
  Table,
  CheckCircle2,
  Clock,
  Layers,
} from "lucide-react";
import { toast } from "sonner";
import { useDocuments, useSummary } from "@/lib/api/queries";
import { apiClient } from "@/lib/api/client";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { SummaryLength, SummaryProfile } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const PROFILES: {
  id: SummaryProfile;
  label: string;
  icon: any;
  desc: string;
}[] = [
  {
    id: "overview",
    label: "Overview",
    icon: Sparkles,
    desc: "High-level summary of core concepts and objectives.",
  },
  {
    id: "detailed",
    label: "Detailed",
    icon: FileText,
    desc: "Comprehensive page-by-page breakdown with nuance.",
  },
  {
    id: "study_notes",
    label: "Study Notes",
    icon: BookOpen,
    desc: "Key takeaways, flashcard concepts, and review bullet points.",
  },
  {
    id: "tables_figures",
    label: "Tables & Figures",
    icon: Table,
    desc: "Extracted visual data, chart trends, and tabular metrics.",
  },
  {
    id: "findings",
    label: "Findings",
    icon: Layers,
    desc: "Empirical results, outcome statistics, and conclusions.",
  },
];

const LENGTHS: SummaryLength[] = ["concise", "standard", "detailed"];

function SummarizerContent() {
  const searchParams = useSearchParams();
  const initialDoc = searchParams.get("doc");

  const { data: documents = [] } = useDocuments();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(
    initialDoc || (documents[0]?.doc_id ?? null)
  );
  const [selectedProfile, setSelectedProfile] = useState<SummaryProfile>("overview");
  const [selectedLength, setSelectedLength] = useState<SummaryLength>("standard");

  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  const {
    data: summaryData,
    isLoading: isSummaryLoading,
    refetch: refetchSummary,
  } = useSummary(selectedDocId, selectedProfile, selectedLength);

  const handleGenerate = async (force: boolean = false) => {
    if (!selectedDocId) {
      toast.error("Please select a document first");
      return;
    }

    setIsGenerating(true);
    try {
      const resp = await apiClient<any>("/summaries", {
        method: "POST",
        body: JSON.stringify({
          doc_id: selectedDocId,
          profile: selectedProfile,
          length: selectedLength,
          force,
        }),
      });

      if (resp.cached) {
        toast.success("Loaded cached summary");
        refetchSummary();
      } else {
        toast.success("Summary job submitted to background worker");
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to trigger summary generation");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopy = () => {
    if (!summaryData?.summary) return;
    navigator.clipboard.writeText(summaryData.summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!summaryData?.summary || !selectedDocId) return;
    const blob = new Blob([summaryData.summary], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedDocId}_${selectedProfile}_summary.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const currentDoc = documents.find((d) => d.doc_id === selectedDocId);

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Configuration Sidebar */}
      <div className="w-80 border-r border-[rgba(255,255,255,0.08)] bg-[#0C0C11] p-6 flex flex-col space-y-6 shrink-0 overflow-y-auto">
        {/* Document Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-[#A1A1AA] uppercase tracking-wider">
            Target Document
          </label>
          <select
            value={selectedDocId || ""}
            onChange={(e) => setSelectedDocId(e.target.value || null)}
            className="w-full px-3 py-2 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#F4F4F5] outline-none focus:border-[#A78BFA]"
          >
            {documents.map((d) => (
              <option key={d.doc_id} value={d.doc_id}>
                {d.filename}
              </option>
            ))}
          </select>
        </div>

        {/* Profile Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-[#A1A1AA] uppercase tracking-wider">
            Analysis Profile
          </label>
          <div className="space-y-2">
            {PROFILES.map((p) => {
              const Icon = p.icon;
              const isSelected = selectedProfile === p.id;
              return (
                <div
                  key={p.id}
                  onClick={() => setSelectedProfile(p.id)}
                  className={cn(
                    "p-3 rounded-lg border text-left cursor-pointer transition-all",
                    isSelected
                      ? "bg-[rgba(167,139,250,0.12)] border-[#A78BFA]/50 text-[#F4F4F5]"
                      : "bg-[#14141B] border-[rgba(255,255,255,0.06)] text-[#A1A1AA] hover:border-[rgba(255,255,255,0.12)]"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Icon className={cn("w-4 h-4", isSelected ? "text-[#A78BFA]" : "text-[#71717A]")} />
                    <span className="text-xs font-semibold">{p.label}</span>
                  </div>
                  <p className="text-[11px] text-[#71717A] mt-1 leading-normal">{p.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Length Control */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-[#A1A1AA] uppercase tracking-wider">
            Length
          </label>
          <div className="grid grid-cols-3 gap-1 p-1 bg-[#14141B] rounded-lg border border-[rgba(255,255,255,0.06)]">
            {LENGTHS.map((len) => (
              <button
                key={len}
                onClick={() => setSelectedLength(len)}
                className={cn(
                  "py-1 text-xs capitalize rounded transition-colors",
                  selectedLength === len
                    ? "bg-[#A78BFA] text-black font-semibold shadow"
                    : "text-[#A1A1AA] hover:text-[#F4F4F5]"
                )}
              >
                {len}
              </button>
            ))}
          </div>
        </div>

        {/* Primary Action Button */}
        <button
          onClick={() => handleGenerate(false)}
          disabled={isGenerating || !selectedDocId}
          className="w-full py-2.5 rounded-lg bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black font-semibold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity shadow-[0_0_15px_rgba(167,139,250,0.25)] flex items-center justify-center gap-2"
        >
          {isGenerating ? <Clock className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          <span>Generate Summary</span>
        </button>
      </div>

      {/* Main Preview */}
      <div className="flex-1 flex flex-col bg-[#050507] p-8 overflow-y-auto">
        <div className="max-w-4xl w-full mx-auto space-y-6">
          {/* Summary Header */}
          <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
            <div>
              <h2 className="text-lg font-bold text-[#F4F4F5] tracking-tight">
                {currentDoc ? currentDoc.filename : "Select a document"}
              </h2>
              <p className="text-xs text-[#A1A1AA] capitalize mt-0.5">
                Profile: {selectedProfile} &bull; Depth: {selectedLength}
              </p>
            </div>

            {summaryData?.summary && (
              <div className="flex items-center gap-2">
                {summaryData.cached && (
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-[#34D399] bg-[#34D399]/10 border border-[#34D399]/20 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" />
                    Cached
                  </span>
                )}
                <button
                  onClick={() => handleGenerate(true)}
                  className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                  title="Force re-generate summary"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button
                  onClick={handleCopy}
                  className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                  title="Copy markdown"
                >
                  {copied ? <Check className="w-4 h-4 text-[#34D399]" /> : <Copy className="w-4 h-4" />}
                </button>
                <button
                  onClick={handleDownload}
                  className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                  title="Download .md file"
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {/* Content Area */}
          {isSummaryLoading || isGenerating ? (
            <div className="p-12 text-center space-y-3">
              <Clock className="w-8 h-8 text-[#A78BFA] mx-auto animate-spin" />
              <p className="text-xs text-[#A1A1AA]">
                Synthesizing multi-page document summary with map-reduce...
              </p>
            </div>
          ) : summaryData?.summary ? (
            <div className="p-6 rounded-[14px] bg-[#0C0C11] border border-[rgba(255,255,255,0.08)] prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-headings:text-[#F4F4F5] prose-headings:font-bold">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                {summaryData.summary}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="p-16 border border-dashed border-[rgba(255,255,255,0.08)] rounded-[14px] text-center space-y-2">
              <FileText className="w-8 h-8 text-[#71717A] mx-auto" />
              <p className="text-sm font-medium text-[#F4F4F5]">No summary generated yet</p>
              <p className="text-xs text-[#71717A]">
                Click Generate Summary to run whole-document synthesis.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SummarizerPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex h-full items-center justify-center text-xs text-[#71717A]">
          Loading summarizer...
        </div>
      }
    >
      <SummarizerContent />
    </React.Suspense>
  );
}
