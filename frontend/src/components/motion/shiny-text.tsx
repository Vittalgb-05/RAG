"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface ShinyTextProps {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
}

export function ShinyText({ text, disabled = false, speed = 5, className }: ShinyTextProps) {
  const animationDuration = `${speed}s`;

  return (
    <span
      className={cn(
        "inline-block bg-clip-text text-transparent bg-[linear-gradient(120deg,rgba(255,255,255,0.4)_0%,rgba(255,255,255,1)_50%,rgba(255,255,255,0.4)_100%)] bg-[length:200%_100%]",
        !disabled && "animate-shine",
        className
      )}
      style={{
        animationDuration,
        backgroundImage:
          "linear-gradient(120deg, rgba(251, 191, 36, 0.6) 0%, rgba(255, 255, 255, 1) 50%, rgba(251, 191, 36, 0.6) 100%)",
      }}
    >
      {text}
    </span>
  );
}
