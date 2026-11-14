"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Maximize2 } from "lucide-react";
import { Source } from "@/lib/api/types";

interface EvidenceLensModalProps {
  source: Source | null;
  onClose: () => void;
}

export function EvidenceLensModal({ source, onClose }: EvidenceLensModalProps) {
  const [zoom, setZoom] = useState(1);
  const [currentPage, setCurrentPage] = useState<number>(source?.page || 1);

  if (!source) return null;

  const docId = source.doc_id;
  const bbox = source.bbox; // [x0, y0, x1, y1] normalized coords
  const imageUrl = `/api/v1/documents/${docId}/pages/${currentPage}/image`;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.5 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/70 z-50 backdrop-blur-xs"
      />

      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="fixed top-0 right-0 h-full w-full max-w-2xl bg-[#0C0C11] border-l border-[rgba(255,255,255,0.12)] p-6 z-50 flex flex-col shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
          <div>
            <h3 className="font-bold text-base text-[#F4F4F5] flex items-center gap-2">
              <span>Evidence Lens</span>
              <span className="font-mono text-xs text-[#22D3EE] font-normal">
                [E{source.rank}]
              </span>
            </h3>
            <p className="text-xs text-[#A1A1AA] truncate">
              {source.filename} &bull; Page {currentPage}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
              className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
              title="Zoom Out"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <span className="text-xs font-mono text-[#71717A] min-w-[40px] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
              className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
              title="Zoom In"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-[#71717A] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Viewport */}
        <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-[#050507]">
          <div
            className="relative border border-[rgba(255,255,255,0.1)] rounded-lg shadow-2xl transition-transform duration-150 origin-center"
            style={{ transform: `scale(${zoom})` }}
          >
            <img
              src={imageUrl}
              alt={`Page ${currentPage}`}
              className="max-h-[70vh] object-contain select-none"
              onError={(e) => {
                // If page image not stored, show fallback representation
                (e.target as HTMLElement).style.display = "none";
              }}
            />

            {/* Bounding Box Highlight Overlay */}
            {bbox && bbox.length === 4 && (
              <div
                className="absolute border-2 border-[#22D3EE] bg-[#A78BFA]/20 rounded animate-pulse pointer-events-none"
                style={{
                  left: `${bbox[0] * 100}%`,
                  top: `${bbox[1] * 100}%`,
                  width: `${(bbox[2] - bbox[0]) * 100}%`,
                  height: `${(bbox[3] - bbox[1]) * 100}%`,
                  boxShadow: "0 0 15px rgba(34, 211, 238, 0.5)",
                }}
              />
            )}
          </div>
        </div>

        {/* Footer Navigation */}
        <div className="pt-4 border-t border-[rgba(255,255,255,0.08)] flex items-center justify-between text-xs text-[#A1A1AA]">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] disabled:opacity-40 hover:text-[#F4F4F5]"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <span className="font-mono text-[#F4F4F5]">Page {currentPage}</span>
            <button
              onClick={() => setCurrentPage((p) => p + 1)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] hover:text-[#F4F4F5]"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {bbox && (
            <span className="font-mono text-[11px] text-[#71717A]">
              BBox: [{bbox.map((v) => v.toFixed(2)).join(", ")}]
            </span>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
