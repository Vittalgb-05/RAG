"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  FileText,
  MessageSquare,
  Library,
  Settings,
  Sparkles,
  Activity,
  PlusCircle,
} from "lucide-react";
import { useAppStore } from "@/lib/store/use-app-store";
import { useCreateChatSession } from "@/lib/api/queries";

export function CommandPalette() {
  const router = useRouter();
  const { commandPaletteOpen, setCommandPaletteOpen } = useAppStore();
  const createChat = useCreateChatSession();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [commandPaletteOpen, setCommandPaletteOpen]);

  if (!commandPaletteOpen) return null;

  const navigateTo = (path: string) => {
    setCommandPaletteOpen(false);
    router.push(path);
  };

  const handleNewChat = () => {
    setCommandPaletteOpen(false);
    createChat.mutate(
      { title: "New Conversation" },
      {
        onSuccess: (session) => {
          router.push(`/chat?session=${session.id}`);
        },
      }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div
        className="fixed inset-0"
        onClick={() => setCommandPaletteOpen(false)}
      />
      <div className="relative w-full max-w-lg rounded-[14px] border border-[rgba(255,255,255,0.12)] bg-[#14141B] shadow-2xl overflow-hidden z-10">
        <Command className="w-full">
          <div className="flex items-center px-4 border-b border-[rgba(255,255,255,0.08)]">
            <Command.Input
              autoFocus
              placeholder="Type a command or navigate..."
              className="w-full h-12 bg-transparent text-sm text-[#F4F4F5] placeholder-[#71717A] outline-none"
            />
          </div>

          <Command.List className="max-h-72 overflow-y-auto p-2 text-sm text-[#A1A1AA]">
            <Command.Empty className="py-6 text-center text-xs text-[#71717A]">
              No results found.
            </Command.Empty>

            <Command.Group heading="Actions" className="px-2 py-1.5 text-[11px] font-semibold text-[#71717A]">
              <Command.Item
                onSelect={handleNewChat}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] hover:text-[#A78BFA] transition-colors"
              >
                <PlusCircle className="w-4 h-4 text-[#A78BFA]" />
                <span>Start New Chat</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-[11px] font-semibold text-[#71717A]">
              <Command.Item
                onSelect={() => navigateTo("/chat")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <MessageSquare className="w-4 h-4 text-[#A1A1AA]" />
                <span>Chat Workspace</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("/library")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <Library className="w-4 h-4 text-[#A1A1AA]" />
                <span>Document Library</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("/summarizer")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <FileText className="w-4 h-4 text-[#A1A1AA]" />
                <span>Document Summarizer</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("/constellation")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <Sparkles className="w-4 h-4 text-[#A1A1AA]" />
                <span>3D Constellation</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("/settings")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <Settings className="w-4 h-4 text-[#A1A1AA]" />
                <span>Settings & Cloud</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("/diagnostics")}
                className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              >
                <Activity className="w-4 h-4 text-[#A1A1AA]" />
                <span>System Diagnostics</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
