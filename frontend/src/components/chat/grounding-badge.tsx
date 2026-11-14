"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";
import { Grounding } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface GroundingBadgeProps {
  grounding?: Grounding;
}

export function GroundingBadge({ grounding }: GroundingBadgeProps) {
  if (!grounding) return null;

  const status = grounding.status;

  const config = {
    grounded: {
      label: "Grounded",
      icon: CheckCircle2,
      border: "border-[#34D399]/30",
      bg: "bg-[#34D399]/10",
      text: "text-[#34D399]",
    },
    partial: {
      label: `Partially Supported (${grounding.uncited_claim_count} uncited)`,
      icon: AlertTriangle,
      border: "border-[#FBBF24]/30",
      bg: "bg-[#FBBF24]/10",
      text: "text-[#FBBF24]",
    },
    unsupported: {
      label: "Unsupported",
      icon: XCircle,
      border: "border-[#F87171]/30",
      bg: "bg-[#F87171]/10",
      text: "text-[#F87171]",
    },
    abstained: {
      label: "Abstained (Insufficient Evidence)",
      icon: XCircle,
      border: "border-[#F87171]/30",
      bg: "bg-[#F87171]/10",
      text: "text-[#F87171]",
    },
    rank_only: {
      label: "Rank Only",
      icon: Info,
      border: "border-[rgba(255,255,255,0.1)]",
      bg: "bg-[rgba(255,255,255,0.05)]",
      text: "text-[#A1A1AA]",
    },
    unverified: {
      label: "Unverified",
      icon: Info,
      border: "border-[rgba(255,255,255,0.1)]",
      bg: "bg-[rgba(255,255,255,0.05)]",
      text: "text-[#71717A]",
    },
  }[status] || {
    label: status,
    icon: Info,
    border: "border-[rgba(255,255,255,0.1)]",
    bg: "bg-[rgba(255,255,255,0.05)]",
    text: "text-[#A1A1AA]",
  };

  const Icon = config.icon;

  return (
    <div className="flex flex-col gap-1.5 mt-2.5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border",
            config.border,
            config.bg,
            config.text
          )}
          title={grounding.caption}
        >
          <Icon className="w-3.5 h-3.5 shrink-0" />
          <span>{config.label}</span>
        </span>

        {grounding.incomplete_context && (
          <span className="text-[11px] text-[#FBBF24] bg-[#FBBF24]/10 border border-[#FBBF24]/30 px-2 py-0.5 rounded-full">
            Incomplete context budget
          </span>
        )}
      </div>

      {grounding.caption && (
        <p className="text-[11px] text-[#71717A] italic ml-1">
          {grounding.caption}
        </p>
      )}
    </div>
  );
}
