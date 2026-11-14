"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { Cpu, HardDrive, Search, ShieldCheck } from "lucide-react";
import { useHealth, useTelemetry } from "@/lib/api/queries";
import { useAppStore } from "@/lib/store/use-app-store";
import { ShinyText } from "@/components/motion/shiny-text";
import { cn } from "@/lib/utils";

export function Topbar() {
  const pathname = usePathname();
  const { setCommandPaletteOpen } = useAppStore();
  const { data: health } = useHealth();
  const { data: telemetry } = useTelemetry();

  const title = pathname.replace(/^\//, "").split("/")[0] || "Chat";
  const displayTitle = title.charAt(0).toUpperCase() + title.slice(1);

  const isCloud = health?.mode === "cloud";
  const isHealthy = health?.status === "healthy";

  return (
    <header className="h-16 border-b border-[rgba(255,255,255,0.08)] bg-[#0C0C11]/80 backdrop-blur-md px-6 flex items-center justify-between shrink-0 z-20">
      {/* Route title / Breadcrumb */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-[#F4F4F5] tracking-tight">
          {displayTitle}
        </h1>
      </div>

      {/* Center / Right controls */}
      <div className="flex items-center gap-4">
        {/* Command palette button */}
        <button
          onClick={() => setCommandPaletteOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[rgba(255,255,255,0.08)] bg-[#14141B] text-xs text-[#A1A1AA] hover:border-[rgba(255,255,255,0.16)] hover:text-[#F4F4F5] transition-all shadow-inner"
        >
          <Search className="w-3.5 h-3.5" />
          <span>Quick actions</span>
          <kbd className="ml-2 px-1.5 py-0.5 text-[10px] bg-[rgba(255,255,255,0.06)] rounded border border-[rgba(255,255,255,0.1)] text-[#71717A]">
            Ctrl+K
          </kbd>
        </button>

        {/* Telemetry meters */}
        {telemetry && (
          <div className="hidden md:flex items-center gap-3 px-3 py-1 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#A1A1AA]">
            {telemetry.gpu ? (
              <div className="flex items-center gap-1.5" title="GPU VRAM Usage">
                <Cpu className="w-3.5 h-3.5 text-[#A78BFA]" />
                <span>
                  {Math.round(telemetry.gpu.used_mb)} / {Math.round(telemetry.gpu.total_mb)} MB
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5" title="Process RAM Usage">
                <HardDrive className="w-3.5 h-3.5 text-[#22D3EE]" />
                <span>{Math.round(telemetry.process.rss_mb)} MB</span>
              </div>
            )}
          </div>
        )}

        {/* Global StatusPill */}
        <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-[rgba(255,255,255,0.08)] bg-[#14141B] text-xs font-medium">
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              !isHealthy
                ? "bg-[#F87171] shadow-[0_0_8px_#F87171]"
                : isCloud
                ? "bg-[#FBBF24] shadow-[0_0_8px_#FBBF24]"
                : "bg-[#34D399] shadow-[0_0_8px_#34D399]"
            )}
          />
          {isCloud ? (
            <ShinyText text="Cloud Active" className="text-xs font-medium" />
          ) : (
            <span className="text-[#A1A1AA] flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-[#34D399]" />
              Local Engine
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
