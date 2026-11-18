"use client";

import React from "react";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { AuroraBg } from "@/components/shell/aurora-bg";

export default function ShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#050507]">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 h-full overflow-hidden relative">
        <Topbar />
        <main className="flex-1 overflow-y-auto relative z-10">{children}</main>
        <AuroraBg />
      </div>
    </div>
  );
}
