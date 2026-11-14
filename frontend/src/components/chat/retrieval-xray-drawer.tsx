"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Search, Layers, Zap, Database } from "lucide-react";
import { apiClient } from "@/lib/api/client";
import { Source } from "@/lib/api/types";

interface ExplanationItem {
  chunk_id: string;
  doc_id: string;
  dense_rank?: number | null;
  dense_score?: number | null;
  fts_rank?: number | null;
  fts_score?: number | null;
  rrf_score: number;
}

interface XRayDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  query: string;
}

export function RetrievalXRayDrawer({ isOpen, onClose, query }: XRayDrawerProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [explanations, setExplanations] = useState<ExplanationItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !query) return;
    setLoading(true);
    apiClient<{ query: string; sources: Source[]; explanations?: ExplanationItem[] }>("/search", {
      method: "POST",
      body: JSON.stringify({ query, k: 8, mode: "hybrid", explain: true }),
    })
      .then((res) => {
        setSources(res.sources || []);
        setExplanations(res.explanations || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isOpen, query]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 z-50 backdrop-blur-xs"
          />

          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed bottom-0 left-0 right-0 max-h-[85vh] bg-[#0C0C11] border-t border-[rgba(255,255,255,0.12)] p-6 z-50 flex flex-col shadow-2xl rounded-t-[20px] overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-[rgba(167,139,250,0.12)] border border-[rgba(167,139,250,0.25)] text-[#A78BFA]">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-base text-[#F4F4F5]">Retrieval X-Ray</h3>
                  <p className="text-xs text-[#A1A1AA] truncate max-w-xl">
                    Query: <span className="text-[#22D3EE] font-mono">"{query}"</span>
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="text-[#71717A] hover:text-[#F4F4F5] p-2 rounded-lg hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {loading ? (
              <div className="py-16 text-center text-xs text-[#71717A] animate-pulse">
                Deconstructing Dense, Sparse (BM25), and RRF ranking signals...
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6 overflow-y-auto pr-2 pb-4">
                {/* Dense Column */}
                <div className="p-4 rounded-[14px] bg-[#14141B] border border-[rgba(255,255,255,0.08)] flex flex-col space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#A78BFA] pb-2 border-b border-[rgba(255,255,255,0.06)]">
                    <Zap className="w-4 h-4" />
                    <span>Dense Vector (Semantic)</span>
                  </div>
                  <div className="space-y-2">
                    {explanations
                      .filter((e) => e.dense_rank !== null && e.dense_rank !== undefined)
                      .sort((a, b) => (a.dense_rank || 99) - (b.dense_rank || 99))
                      .map((e, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-[#0C0C11] border border-[rgba(255,255,255,0.04)] text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[#A78BFA] font-bold">
                              Rank #{e.dense_rank}
                            </span>
                            <span className="text-[11px] text-[#A1A1AA] font-mono">
                              Cosine: {e.dense_score?.toFixed(3)}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#71717A] truncate font-mono">
                            {e.chunk_id}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Keyword / Sparse Column */}
                <div className="p-4 rounded-[14px] bg-[#14141B] border border-[rgba(255,255,255,0.08)] flex flex-col space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#22D3EE] pb-2 border-b border-[rgba(255,255,255,0.06)]">
                    <Search className="w-4 h-4" />
                    <span>Keyword BM25 (Lexical)</span>
                  </div>
                  <div className="space-y-2">
                    {explanations
                      .filter((e) => e.fts_rank !== null && e.fts_rank !== undefined)
                      .sort((a, b) => (a.fts_rank || 99) - (b.fts_rank || 99))
                      .map((e, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-[#0C0C11] border border-[rgba(255,255,255,0.04)] text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[#22D3EE] font-bold">
                              Rank #{e.fts_rank}
                            </span>
                            <span className="text-[11px] text-[#A1A1AA] font-mono">
                              BM25: {e.fts_score?.toFixed(3)}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#71717A] truncate font-mono">
                            {e.chunk_id}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Fused RRF Column */}
                <div className="p-4 rounded-[14px] bg-[#14141B] border border-[rgba(167,139,250,0.2)] flex flex-col space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#34D399] pb-2 border-b border-[rgba(255,255,255,0.06)]">
                    <Database className="w-4 h-4" />
                    <span>Fused RRF (Reciprocal Rank)</span>
                  </div>
                  <div className="space-y-2">
                    {sources.map((s, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 rounded-lg bg-[#0C0C11] border border-[rgba(52,211,153,0.2)] text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[#34D399] font-bold">
                            Final #{s.rank}
                          </span>
                          <span className="text-[11px] text-[#A1A1AA] font-mono">
                            Score: {s.score?.toFixed(4)}
                          </span>
                        </div>
                        <p className="text-[11px] text-[#F4F4F5] truncate font-medium">
                          {s.filename} (p. {s.page ?? "N/A"})
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
