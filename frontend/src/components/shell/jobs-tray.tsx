"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, Loader2, XCircle } from "lucide-react";
import { useCancelJob, useJobs } from "@/lib/api/queries";

export function JobsTray() {
  const { data: jobs = [] } = useJobs();
  const cancelMutation = useCancelJob();
  const [collapsed, setCollapsed] = useState(false);

  const activeJobs = jobs.filter((j) => ["queued", "running"].includes(j.status));
  if (activeJobs.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 w-80 rounded-[14px] border border-[rgba(255,255,255,0.12)] bg-[#14141B] shadow-[0_10px_40px_rgba(0,0,0,0.6)] overflow-hidden">
      <div
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-between px-4 py-2.5 bg-[#0C0C11] border-b border-[rgba(255,255,255,0.08)] cursor-pointer select-none"
      >
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 text-[#A78BFA] animate-spin" />
          <span className="text-xs font-semibold text-[#F4F4F5]">
            Tasks in progress ({activeJobs.length})
          </span>
        </div>
        {collapsed ? (
          <ChevronUp className="w-4 h-4 text-[#71717A]" />
        ) : (
          <ChevronDown className="w-4 h-4 text-[#71717A]" />
        )}
      </div>

      {!collapsed && (
        <div className="p-3 max-h-60 overflow-y-auto space-y-3">
          {activeJobs.map((job) => (
            <div
              key={job.job_id}
              className="p-2.5 rounded-lg bg-[#0C0C11] border border-[rgba(255,255,255,0.06)] space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[#F4F4F5] capitalize">
                  {job.kind}: {job.stage}
                </span>
                <button
                  onClick={() => cancelMutation.mutate(job.job_id)}
                  disabled={cancelMutation.isPending}
                  className="text-[#71717A] hover:text-[#F87171] transition-colors"
                  title="Cancel job"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>

              {job.message && (
                <p className="text-[11px] text-[#A1A1AA] truncate">{job.message}</p>
              )}

              {/* Progress bar */}
              <div className="w-full h-1.5 rounded-full bg-[rgba(255,255,255,0.06)] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(5, job.pct || 10))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
