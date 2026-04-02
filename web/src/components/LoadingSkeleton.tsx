"use client";

interface LoadingSkeletonProps {
  rows?: number;
  height?: number;
}

export default function LoadingSkeleton({ rows = 3, height = 60 }: LoadingSkeletonProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{
            height,
            borderRadius: 8,
            background: "var(--bg-secondary)",
            animation: "pulse 1.5s ease-in-out infinite",
            opacity: 1 - i * 0.15,
          }}
        />
      ))}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}
