interface MetricCardProps {
  label: string;
  value: string;
  className?: string;
  subtitle?: string;
}

export default function MetricCard({ label, value, className = "", subtitle }: MetricCardProps) {
  return (
    <div className="card">
      <div className={`metric-value ${className}`}>{value}</div>
      <div className="metric-label">{label}</div>
      {subtitle && (
        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 4 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
}
