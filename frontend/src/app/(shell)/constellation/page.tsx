"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Sparkles, MessageSquare, Maximize2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { useConstellation } from "@/lib/api/queries";
import { apiClient } from "@/lib/api/client";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { EmbeddingPoint } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#A78BFA", "#22D3EE", "#F472B6", "#34D399", "#FBBF24"];

export default function ConstellationPage() {
  const router = useRouter();
  const { data: constellationData, isLoading } = useConstellation();
  const points = constellationData?.points || [];

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [queryText, setQueryText] = useState("");
  const [queryPoint, setQueryPoint] = useState<[number, number, number] | null>(null);
  const [hitChunkIds, setHitChunkIds] = useState<string[]>([]);
  const [selectedPoint, setSelectedPoint] = useState<EmbeddingPoint | null>(null);

  // 3D rotation angles
  const [rotX, setRotX] = useState(0.2);
  const [rotY, setRotY] = useState(0.4);
  const isDraggingRef = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });

  const docColorMap = useRef<Map<string, string>>(new Map());

  // Assign document colors
  points.forEach((p) => {
    if (!docColorMap.current.has(p.doc_id)) {
      const color = PALETTE[docColorMap.current.size % PALETTE.length];
      docColorMap.current.set(p.doc_id, color);
    }
  });

  const handleQueryTrace = async () => {
    if (!queryText.trim()) return;
    try {
      const res = await apiClient<{ point: [number, number, number]; retrieved_chunk_ids: string[] }>(
        "/visualize/query-trace",
        {
          method: "POST",
          body: JSON.stringify({ query: queryText, k: 5 }),
        }
      );
      setQueryPoint(res.point);
      setHitChunkIds(res.retrieved_chunk_ids);
      toast.success(`Traced query beacon to top ${res.retrieved_chunk_ids.length} chunks`);
    } catch (err: any) {
      toast.error(err.message || "Query trace failed");
    }
  };

  // Render 3D projection onto 2D canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const scale = Math.min(cx, cy) * 0.7;

      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);

      // Project function
      const project = (x: number, y: number, z: number) => {
        // Rotate Y
        const x1 = x * cosY - z * sinY;
        const z1 = x * sinY + z * cosY;
        // Rotate X
        const y2 = y * cosX - z1 * sinX;
        const z2 = y * sinX + z1 * cosX;

        const distance = 3.5;
        const pz = z2 + distance;
        const fov = scale / (pz > 0.1 ? pz : 0.1);

        return {
          px: cx + x1 * fov,
          py: cy + y2 * fov,
          pz,
        };
      };

      // Draw lines to query hits if active
      if (queryPoint && hitChunkIds.length > 0) {
        const qProj = project(queryPoint[0], queryPoint[1], queryPoint[2]);
        points.forEach((pt) => {
          if (hitChunkIds.includes(pt.chunk_id)) {
            const pProj = project(pt.point[0], pt.point[1], pt.point[2]);
            ctx.beginPath();
            ctx.moveTo(qProj.px, qProj.py);
            ctx.lineTo(pProj.px, pProj.py);
            ctx.strokeStyle = "rgba(34, 211, 238, 0.4)";
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }
        });

        // Draw Query Beacon
        ctx.beginPath();
        ctx.arc(qProj.px, qProj.py, 8, 0, Math.PI * 2);
        ctx.fillStyle = "#22D3EE";
        ctx.shadowColor = "#22D3EE";
        ctx.shadowBlur = 15;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Draw points
      points.forEach((pt) => {
        const isHit = hitChunkIds.includes(pt.chunk_id);
        const isSelected = selectedPoint?.chunk_id === pt.chunk_id;
        const proj = project(pt.point[0], pt.point[1], pt.point[2]);

        const color = docColorMap.current.get(pt.doc_id) || "#A78BFA";
        const alpha = hitChunkIds.length > 0 && !isHit ? 0.2 : 0.85;

        ctx.beginPath();
        ctx.arc(proj.px, proj.py, isHit || isSelected ? 5.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = alpha;
        if (isHit || isSelected) {
          ctx.shadowColor = color;
          ctx.shadowBlur = 10;
        }
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 1.0;
      });
    };

    render();
  }, [points, rotX, rotY, queryPoint, hitChunkIds, selectedPoint]);

  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    lastMousePos.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    const deltaX = e.clientX - lastMousePos.current.x;
    const deltaY = e.clientY - lastMousePos.current.y;
    lastMousePos.current = { x: e.clientX, y: e.clientY };

    setRotY((y) => y + deltaX * 0.008);
    setRotX((x) => x + deltaY * 0.008);
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  return (
    <div className="relative h-full w-full flex flex-col bg-[#050507] overflow-hidden select-none">
      {/* Top Floating Controls */}
      <div className="absolute top-6 left-6 z-20 flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-[12px] bg-[#0C0C11]/90 border border-[rgba(255,255,255,0.1)] backdrop-blur-md shadow-2xl">
          <Search className="w-4 h-4 text-[#A1A1AA]" />
          <input
            type="text"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleQueryTrace()}
            placeholder="Trace query beacon in 3D..."
            className="w-64 bg-transparent text-xs text-[#F4F4F5] placeholder-[#71717A] outline-none"
          />
          <button
            onClick={handleQueryTrace}
            className="px-2.5 py-1 rounded-lg bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black text-xs font-semibold hover:opacity-90 transition-opacity"
          >
            Trace
          </button>
        </div>

        <button
          onClick={() => {
            setRotX(0.2);
            setRotY(0.4);
            setQueryPoint(null);
            setHitChunkIds([]);
          }}
          className="p-2 rounded-[12px] bg-[#0C0C11]/90 border border-[rgba(255,255,255,0.1)] text-[#A1A1AA] hover:text-[#F4F4F5] backdrop-blur-md"
          title="Reset viewpoint"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Main 3D Canvas */}
      <div
        className="flex-1 w-full h-full cursor-grab active:cursor-grabbing flex items-center justify-center relative"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        {isLoading ? (
          <div className="flex flex-col items-center gap-2 text-xs text-[#A1A1AA]">
            <Sparkles className="w-6 h-6 text-[#A78BFA] animate-spin" />
            <span>Projecting embeddings into 3D manifold...</span>
          </div>
        ) : points.length === 0 ? (
          <div className="text-center space-y-2 text-[#71717A]">
            <Sparkles className="w-8 h-8 mx-auto" />
            <p className="text-sm font-medium text-[#F4F4F5]">No vector embeddings found</p>
            <p className="text-xs">Index a document in the Library to explore the constellation.</p>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            width={1200}
            height={800}
            className="w-full h-full object-contain"
          />
        )}
      </div>

      {/* Bottom Document Palette Legend */}
      <div className="absolute bottom-6 left-6 z-20 flex flex-wrap gap-2 max-w-xl">
        {Array.from(docColorMap.current.entries()).map(([docId, color]) => (
          <div
            key={docId}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#0C0C11]/80 border border-[rgba(255,255,255,0.08)] backdrop-blur-md text-[11px] text-[#F4F4F5]"
          >
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="truncate max-w-[120px]">{docId}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
