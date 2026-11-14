"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  MessageSquare,
  Library,
  FileText,
  Sparkles,
  Settings,
  Activity,
  ChevronLeft,
  ChevronRight,
  Database,
} from "lucide-react";
import { useAppStore } from "@/lib/store/use-app-store";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Chat", href: "/chat", icon: MessageSquare },
  { label: "Library", href: "/library", icon: Library },
  { label: "Summarizer", href: "/summarizer", icon: FileText },
  { label: "Constellation", href: "/constellation", icon: Sparkles },
  { label: "Settings", href: "/settings", icon: Settings },
  { label: "Diagnostics", href: "/diagnostics", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();

  return (
    <motion.aside
      animate={{ width: sidebarCollapsed ? 72 : 264 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="relative flex flex-col border-r border-[rgba(255,255,255,0.08)] bg-[#0C0C11] h-screen select-none shrink-0"
    >
      {/* Brand header */}
      <div className="flex items-center h-16 px-4 border-b border-[rgba(255,255,255,0.08)]">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#A78BFA] to-[#22D3EE] flex items-center justify-center shrink-0 shadow-[0_0_15px_rgba(167,139,250,0.3)]">
            <Database className="w-5 h-5 text-black" />
          </div>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col truncate"
            >
              <span className="font-semibold text-sm tracking-wide text-[#F4F4F5]">
                RAG Assistant
              </span>
              <span className="text-[11px] text-[#A1A1AA]">Local-First AI</span>
            </motion.div>
          )}
        </div>
      </div>

      {/* Navigation items */}
      <nav className="flex-1 px-2.5 py-4 space-y-1.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative flex items-center gap-3.5 px-3 py-2.5 rounded-[10px] text-sm font-medium transition-colors",
                isActive
                  ? "text-[#F4F4F5]"
                  : "text-[#A1A1AA] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.04)]"
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="activeNavIndicator"
                  className="absolute inset-0 rounded-[10px] bg-gradient-to-r from-[rgba(167,139,250,0.15)] to-[rgba(34,211,238,0.05)] border border-[rgba(167,139,250,0.3)] shadow-[0_0_15px_rgba(167,139,250,0.15)]"
                  transition={{ type: "spring", stiffness: 350, damping: 30 }}
                />
              )}
              <Icon
                className={cn(
                  "w-5 h-5 shrink-0 relative z-10 transition-colors",
                  isActive ? "text-[#A78BFA]" : "text-[#71717A]"
                )}
              />
              {!sidebarCollapsed && (
                <span className="relative z-10 truncate">{item.label}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse button */}
      <div className="p-3 border-t border-[rgba(255,255,255,0.08)]">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center p-2 rounded-lg text-[#71717A] hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.05)] transition-colors"
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <div className="flex items-center gap-2 w-full px-1">
              <ChevronLeft className="w-5 h-5" />
              <span className="text-xs">Collapse</span>
            </div>
          )}
        </button>
      </div>
    </motion.aside>
  );
}
