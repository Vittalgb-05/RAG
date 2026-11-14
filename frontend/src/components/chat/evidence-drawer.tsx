"use client";

import React from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, ExternalLink, FileText } from "lucide-react";
import { useAppStore } from "@/lib/store/use-app-store";

export function EvidenceDrawer() {
  const { selectedSource, setSelectedSource } = useAppStore();

  return (
    <AnimatePresence>
      {selectedSource && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.4 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedSource(null)}
            className="fixed inset-0 bg-black/60 z-40 backdrop-blur-xs"
          />

          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed top-0 right-0 h-full w-full max-w-md bg-[#0C0C11] border-l border-[rgba(255,255,255,0.12)] p-6 z-50 flex flex-col shadow-2xl overflow-y-auto"
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded font-mono text-xs font-semibold bg-[rgba(167,139,250,0.15)] text-[#A78BFA] border border-[rgba(167,139,250,0.3)]">
                  [E{selectedSource.rank}]
                </span>
                <span className="text-sm font-semibold text-[#F4F4F5]">Evidence Source</span>
              </div>
              <button
                onClick={() => setSelectedSource(null)}
                className="text-[#71717A] hover:text-[#F4F4F5] p-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Document metadata */}
            <div className="mt-4 p-3.5 rounded-[10px] bg-[#14141B] border border-[rgba(255,255,255,0.06)] space-y-2">
              <div className="flex items-start gap-2.5">
                <FileText className="w-4 h-4 text-[#A78BFA] shrink-0 mt-0.5" />
                <div className="truncate">
                  <p className="text-xs font-medium text-[#F4F4F5] truncate">
                    {selectedSource.filename}
                  </p>
                  <p className="text-[11px] text-[#A1A1AA]">
                    Page {selectedSource.page ?? "Unknown"} &bull; Document ID: {selectedSource.doc_id}
                  </p>
                </div>
              </div>
            </div>

            {/* Extracted snippet text */}
            <div className="mt-6 flex-1 space-y-2">
              <span className="text-xs font-semibold text-[#A1A1AA] uppercase tracking-wider">
                Extracted Snippet
              </span>
              <div className="p-4 rounded-[10px] bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-sm text-[#F4F4F5] leading-relaxed font-sans select-text">
                {selectedSource.preview}
              </div>
            </div>

            {/* Score & bbox details */}
            {selectedSource.score !== null && (
              <div className="mt-4 pt-4 border-t border-[rgba(255,255,255,0.08)] flex items-center justify-between text-xs text-[#71717A]">
                <span>Hybrid RRF Score:</span>
                <span className="font-mono text-[#22D3EE] font-medium">
                  {selectedSource.score?.toFixed(4)}
                </span>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
