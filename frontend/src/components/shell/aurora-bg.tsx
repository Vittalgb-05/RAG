"use client";

import React from "react";

export function AuroraBg() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      <div
        className="absolute -top-[40%] left-[20%] h-[80vw] w-[80vw] rounded-full opacity-[0.08] blur-[120px]"
        style={{
          background:
            "radial-gradient(circle, #A78BFA 0%, #22D3EE 50%, transparent 80%)",
        }}
      />
      <div
        className="absolute top-[60%] -left-[20%] h-[60vw] w-[60vw] rounded-full opacity-[0.05] blur-[100px]"
        style={{
          background:
            "radial-gradient(circle, #22D3EE 0%, #F472B6 40%, transparent 80%)",
        }}
      />
    </div>
  );
}
