"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Copy,
  Check,
  RefreshCw,
  Server,
  FileCode,
} from "lucide-react";
import { toast } from "sonner";
import { useHealth } from "@/lib/api/queries";
import { apiClient } from "@/lib/api/client";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { cn } from "@/lib/utils";

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

interface DiagnosticsData {
  health: any;
  tombstones: string[];
  degraded_documents: any[];
  hydration: any;
}

export default function DiagnosticsPage() {
  const { data: health } = useHealth();
  const [diagnostics, setDiagnostics] = useState<DiagnosticsData | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchDiagnostics = async () => {
    try {
      const data = await apiClient<DiagnosticsData>("/diagnostics");
      setDiagnostics(data);
    } catch {}
  };

  const fetchLogs = async () => {
    try {
      const logData = await apiClient<LogEntry[]>("/diagnostics/logs?lines=100");
      setLogs(logData);
    } catch {}
  };

  useEffect(() => {
    fetchDiagnostics();
    fetchLogs();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchLogs();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const handleCopyLogs = () => {
    const text = logs.map((l) => `${l.timestamp} [${l.level}] ${l.message}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isHealthy = health?.status === "healthy";

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8">
      {/* Provider Health Card */}
      <SpotlightCard className="p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.08)] pb-4">
          <div className="flex items-center gap-3">
            <Server className="w-5 h-5 text-[#A78BFA]" />
            <h3 className="font-bold text-base text-[#F4F4F5]">Engine & Provider Health</h3>
          </div>

          <span
            className={cn(
              "px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5",
              isHealthy
                ? "bg-[#34D399]/10 text-[#34D399] border border-[#34D399]/20"
                : "bg-[#F87171]/10 text-[#F87171] border border-[#F87171]/20"
            )}
          >
            {isHealthy ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {health?.status.toUpperCase() || "CHECKING"}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-[#A1A1AA]">
          <div>
            Mode: <span className="text-[#F4F4F5] font-semibold capitalize">{health?.mode}</span>
          </div>
          <div>
            Provider: <span className="text-[#F4F4F5] font-semibold">{health?.provider}</span>
          </div>
          <div>
            Context Window:{" "}
            <span className="text-[#F4F4F5] font-semibold">
              {health?.capabilities.context_window?.toLocaleString()} tokens
            </span>
          </div>
          <div>
            Vision Support:{" "}
            <span className="text-[#F4F4F5] font-semibold">
              {health?.capabilities.supports_vision ? "Enabled" : "Disabled"}
            </span>
          </div>
        </div>

        {health?.runtime.llama_server_version && (
          <p className="text-[11px] text-[#71717A] pt-2 border-t border-[rgba(255,255,255,0.06)]">
            llama.cpp binary version: {health.runtime.llama_server_version} (build:{" "}
            {health.runtime.build || "native"})
          </p>
        )}
      </SpotlightCard>

      {/* Index Integrity & Degradation */}
      <SpotlightCard className="p-6 space-y-4">
        <h3 className="font-bold text-base text-[#F4F4F5]">Index Integrity & Hydration</h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="p-3 rounded-lg bg-[#14141B]">
            <span className="text-[#A1A1AA]">Restored Docs</span>
            <p className="text-lg font-bold text-[#F4F4F5] mt-1">
              {diagnostics?.hydration?.restored ?? 0}
            </p>
          </div>
          <div className="p-3 rounded-lg bg-[#14141B]">
            <span className="text-[#A1A1AA]">Auto-Repaired</span>
            <p className="text-lg font-bold text-[#22D3EE] mt-1">
              {diagnostics?.hydration?.repaired ?? 0}
            </p>
          </div>
          <div className="p-3 rounded-lg bg-[#14141B]">
            <span className="text-[#A1A1AA]">Failed Docs</span>
            <p className="text-lg font-bold text-[#F87171] mt-1">
              {diagnostics?.hydration?.failed ?? 0}
            </p>
          </div>
          <div className="p-3 rounded-lg bg-[#14141B]">
            <span className="text-[#A1A1AA]">Tombstones Consumed</span>
            <p className="text-lg font-bold text-[#34D399] mt-1">
              {diagnostics?.hydration?.tombstones_consumed ?? 0}
            </p>
          </div>
        </div>

        {diagnostics?.degraded_documents && diagnostics.degraded_documents.length > 0 ? (
          <div className="mt-4 p-4 rounded-lg bg-[#FBBF24]/10 border border-[#FBBF24]/20 space-y-2">
            <span className="text-xs font-semibold text-[#FBBF24] flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" /> Degraded Documents Needing Repair:
            </span>
            <ul className="text-xs text-[#A1A1AA] list-disc list-inside">
              {diagnostics.degraded_documents.map((d: any) => (
                <li key={d.doc_id}>
                  {d.filename} ({d.doc_id}) - Missing vectors
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-xs text-[#34D399] flex items-center gap-1.5 mt-2">
            <CheckCircle2 className="w-4 h-4" /> All indexed vectors and LanceDB tables are healthy.
          </p>
        )}
      </SpotlightCard>

      {/* Redacted Logs Viewer */}
      <SpotlightCard className="p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.08)] pb-4">
          <div className="flex items-center gap-2">
            <FileCode className="w-4 h-4 text-[#A78BFA]" />
            <h3 className="font-bold text-base text-[#F4F4F5]">Server Logs (Redacted)</h3>
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-[#A1A1AA] cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded bg-[#14141B]"
              />
              <span>Auto-refresh (5s)</span>
            </label>

            <button
              onClick={fetchLogs}
              className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
              title="Refresh logs"
            >
              <RefreshCw className="w-4 h-4" />
            </button>

            <button
              onClick={handleCopyLogs}
              className="p-1.5 rounded-lg text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
              title="Copy all logs"
            >
              {copied ? <Check className="w-4 h-4 text-[#34D399]" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div className="h-80 overflow-y-auto rounded-lg bg-[#050507] p-4 font-mono text-[11px] text-[#A1A1AA] space-y-1 select-text">
          {logs.length === 0 ? (
            <p className="text-[#71717A] text-center py-10">No recent logs found.</p>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className="flex gap-2 leading-relaxed">
                <span className="text-[#71717A] shrink-0">{log.timestamp}</span>
                <span
                  className={cn(
                    "font-bold shrink-0",
                    log.level === "ERROR"
                      ? "text-[#F87171]"
                      : log.level === "WARNING"
                      ? "text-[#FBBF24]"
                      : "text-[#22D3EE]"
                  )}
                >
                  [{log.level}]
                </span>
                <span className="text-[#F4F4F5] break-all">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </SpotlightCard>
    </div>
  );
}
