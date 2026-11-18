"use client";

import React from "react";
import { SentenceSupport, Source } from "@/lib/api/types";
import { CitationPill } from "./citation-pill";
import { cn } from "@/lib/utils";

interface GroundingHeatmapProps {
  sentenceSupport?: SentenceSupport[];
  sources?: Source[];
}

export function GroundingHeatmap({ sentenceSupport, sources }: GroundingHeatmapProps) {
  if (!sentenceSupport || sentenceSupport.length === 0) return null;

  return (
    <div className="space-y-1.5 leading-relaxed text-sm">
      {sentenceSupport.map((item, idx) => (
        <span
          key={idx}
          className={cn(
            "relative px-1 py-0.5 rounded transition-colors group",
            item.supported
              ? "border-b-2 border-[#34D399]/60 hover:bg-[#34D399]/10"
              : "border-b-2 border-[#F87171]/60 hover:bg-[#F87171]/10"
          )}
        >
          <span>{item.text} </span>

          {/* Render citations directly inside each sentence block */}
          {item.cited_ranks?.map((rank) => (
            <CitationPill key={rank} rank={rank} sources={sources} />
          ))}

          {/* Hover popup tooltip */}
          <span className="pointer-events-none absolute bottom-full left-0 mb-1 hidden group-hover:block z-30 w-64 p-2 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.12)] text-[11px] text-[#F4F4F5] shadow-xl">
            <span className="block font-semibold">
              {item.supported ? "Supported claim" : "Unverified claim"}
            </span>
            <span className="text-[#A1A1AA]">
              Support score: {(item.score * 100).toFixed(0)}%
            </span>
          </span>
        </span>
      ))}
    </div>
  );
}
