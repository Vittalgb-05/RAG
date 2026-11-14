"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { Copy, Check, Flame, Share2, Sparkles, User } from "lucide-react";
import { ChatMessage } from "@/lib/api/types";
import { GroundingBadge } from "./grounding-badge";
import { GroundingHeatmap } from "./grounding-heatmap";
import { CitationPill } from "./citation-pill";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasHeatmap = Boolean(
    message.grounding?.sentence_support &&
      message.grounding.sentence_support.length > 0
  );

  return (
    <div
      className={cn(
        "flex gap-3.5 my-4 max-w-3xl",
        isUser ? "ml-auto flex-row-reverse" : "mr-auto flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center shrink-0 border text-xs",
          isUser
            ? "bg-[#14141B] border-[rgba(255,255,255,0.12)] text-[#F4F4F5]"
            : "bg-gradient-to-br from-[#A78BFA] to-[#22D3EE] border-transparent text-black shadow-[0_0_12px_rgba(167,139,250,0.3)]"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
      </div>

      {/* Bubble body */}
      <div className="flex flex-col flex-1 overflow-hidden">
        <div
          className={cn(
            "p-4 rounded-[14px] text-sm leading-relaxed",
            isUser
              ? "bg-[rgba(167,139,250,0.12)] border border-[rgba(167,139,250,0.25)] text-[#F4F4F5] rounded-tr-none"
              : "bg-[#0C0C11] border border-[rgba(255,255,255,0.08)] text-[#F4F4F5] rounded-tl-none shadow-sm"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : showHeatmap && hasHeatmap ? (
            <GroundingHeatmap
              sentenceSupport={message.grounding?.sentence_support}
              sources={message.sources}
            />
          ) : (
            <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-[#14141B] prose-pre:border prose-pre:border-[rgba(255,255,255,0.08)]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeSanitize]}
                components={{
                  // Render [E1] citation references as custom interactive pills
                  p: ({ children }) => {
                    return <p className="mb-3 last:mb-0">{children}</p>;
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {!isUser && message.grounding && (
            <GroundingBadge grounding={message.grounding} />
          )}
        </div>

        {/* Action bar for assistant messages */}
        {!isUser && (
          <div className="flex items-center gap-1.5 mt-1.5 px-1 text-xs text-[#71717A]">
            <button
              onClick={handleCopy}
              className="p-1 rounded hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)] transition-colors"
              title="Copy answer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-[#34D399]" /> : <Copy className="w-3.5 h-3.5" />}
            </button>

            {hasHeatmap && (
              <button
                onClick={() => setShowHeatmap(!showHeatmap)}
                className={cn(
                  "flex items-center gap-1 px-2 py-0.5 rounded text-[11px] transition-colors",
                  showHeatmap
                    ? "bg-[#A78BFA]/20 text-[#A78BFA]"
                    : "hover:text-[#F4F4F5] hover:bg-[rgba(255,255,255,0.06)]"
                )}
                title="Toggle grounding heatmap"
              >
                <Flame className="w-3 h-3" />
                <span>Heatmap</span>
              </button>
            )}

            {message.usage && (
              <span className="ml-auto text-[10px] text-[#71717A]">
                TTFT: {Math.round(message.usage.ttft_ms)}ms &bull; {message.usage.tokens} tokens
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
