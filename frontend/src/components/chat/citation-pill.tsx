"use client";

import React from "react";
import { Source } from "@/lib/api/types";
import { useAppStore } from "@/lib/store/use-app-store";

interface CitationPillProps {
  rank: number;
  sources?: Source[];
}

export function CitationPill({ rank, sources }: CitationPillProps) {
  const { setSelectedSource } = useAppStore();
  const matchedSource = sources?.find((s) => s.rank === rank);

  return (
    <button
      onClick={() => matchedSource && setSelectedSource(matchedSource)}
      className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs font-mono font-medium rounded bg-[rgba(167,139,250,0.12)] border border-[rgba(167,139,250,0.25)] text-[#A78BFA] hover:bg-[rgba(167,139,250,0.25)] hover:border-[#A78BFA] transition-all cursor-pointer align-baseline"
      title={
        matchedSource
          ? `${matchedSource.filename} (p. ${matchedSource.page ?? "N/A"})`
          : `Source [E${rank}]`
      }
    >
      E{rank}
    </button>
  );
}
