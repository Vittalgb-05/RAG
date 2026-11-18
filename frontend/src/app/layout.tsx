"use client";

import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { CommandPalette } from "@/components/shell/command-palette";
import { EvidenceDrawer } from "@/components/chat/evidence-drawer";
import { JobsTray } from "@/components/shell/jobs-tray";
import "@/styles/globals.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <html lang="en" className="dark">
      <head>
        <title>RAG Assistant</title>
        <meta
          name="description"
          content="Local-First, Multimodal PDF Intelligence and Grounded Assistant"
        />
      </head>
      <body className="bg-[#050507] text-[#F4F4F5] antialiased select-none">
        <QueryClientProvider client={queryClient}>
          {children}
          <CommandPalette />
          <EvidenceDrawer />
          <JobsTray />
          <Toaster
            theme="dark"
            position="bottom-left"
            toastOptions={{
              style: {
                background: "#14141B",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                color: "#F4F4F5",
              },
            }}
          />
        </QueryClientProvider>
      </body>
    </html>
  );
}
