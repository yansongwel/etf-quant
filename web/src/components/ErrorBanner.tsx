"use client";

interface ErrorBannerProps {
  message?: string;
  onRetry?: () => void;
}

export default function ErrorBanner({
  message = "数据加载失败，请检查后端服务是否正常运行",
  onRetry,
}: ErrorBannerProps) {
  return (
    <div
      style={{
        padding: "1rem 1.25rem",
        borderRadius: 8,
        background: "rgba(239, 68, 68, 0.08)",
        border: "1px solid rgba(239, 68, 68, 0.3)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        margin: "1rem 0",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <span style={{ fontSize: "1.2rem" }}>⚠️</span>
        <span style={{ color: "#ef4444", fontSize: "0.9rem" }}>{message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: "0.4rem 1rem",
            borderRadius: 6,
            border: "1px solid rgba(239, 68, 68, 0.4)",
            background: "transparent",
            color: "#ef4444",
            cursor: "pointer",
            fontSize: "0.8rem",
            whiteSpace: "nowrap",
          }}
        >
          重试
        </button>
      )}
    </div>
  );
}
