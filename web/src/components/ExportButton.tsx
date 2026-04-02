"use client";

import { useCallback, useRef } from "react";

interface ExportButtonProps {
  /** CSS selector or ref ID for the element to capture */
  targetId: string;
  /** Filename without extension */
  filename?: string;
  /** Button label */
  label?: string;
}

export default function ExportButton({
  targetId,
  filename = "export",
  label = "导出图片",
}: ExportButtonProps) {
  const busyRef = useRef(false);

  const handleExport = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;

    try {
      const { default: html2canvas } = await import("html2canvas");
      const el = document.getElementById(targetId);
      if (!el) return;

      const canvas = await html2canvas(el, {
        backgroundColor: "#0f172a",
        scale: 2,
        useCORS: true,
        logging: false,
      });

      const link = document.createElement("a");
      link.download = `${filename}-${new Date().toISOString().slice(0, 10)}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch {
      /* silent — export is optional */
    } finally {
      busyRef.current = false;
    }
  }, [targetId, filename]);

  return (
    <button
      onClick={handleExport}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "4px 10px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "transparent",
        color: "var(--text-secondary)",
        fontSize: "0.7rem",
        cursor: "pointer",
        transition: "all 0.15s",
      }}
      title="导出为 PNG 图片"
    >
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1={12} y1={15} x2={12} y2={3} />
      </svg>
      {label}
    </button>
  );
}
