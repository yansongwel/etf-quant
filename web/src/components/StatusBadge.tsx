interface StatusBadgeProps {
  status: "connected" | "unavailable" | "ok" | "error";
  label: string;
}

export default function StatusBadge({ status, label }: StatusBadgeProps) {
  const isOk = status === "connected" || status === "ok";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: "0.8rem",
        color: isOk ? "var(--green)" : "var(--text-secondary)",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: isOk ? "var(--green)" : "var(--border)",
        }}
      />
      {label}
    </span>
  );
}
