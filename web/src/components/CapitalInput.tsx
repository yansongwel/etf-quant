"use client";

import { useState, useEffect } from "react";

const PRESETS = [
  { label: "10万", value: 100000 },
  { label: "30万", value: 300000 },
  { label: "50万", value: 500000 },
  { label: "80万", value: 800000 },
  { label: "100万", value: 1000000 },
];

interface CapitalInputProps {
  value: number;
  onChange: (value: number) => void;
  /** Compact mode: single-line, smaller text. Default false. */
  compact?: boolean;
}

export default function CapitalInput({ value, onChange, compact = false }: CapitalInputProps) {
  const [inputValue, setInputValue] = useState(String(value / 10000));

  // Sync input when external value changes (e.g., preset click)
  useEffect(() => {
    const expected = String(value / 10000);
    if (inputValue !== expected && !document.activeElement?.closest("[data-capital-input]")) {
      setInputValue(expected);
    }
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleInput = (raw: string) => {
    setInputValue(raw);
    const v = parseFloat(raw);
    if (!isNaN(v) && v >= 1 && v <= 10000) {
      onChange(v * 10000);
    }
  };

  const handlePreset = (v: number) => {
    onChange(v);
    setInputValue(String(v / 10000));
  };

  const fontSize = compact ? "0.95rem" : "1.2rem";
  const btnPad = compact ? "0.35rem 0.6rem" : "0.45rem 0.75rem";
  const btnFont = compact ? "0.75rem" : "0.8rem";

  return (
    <div data-capital-input style={{ display: "flex", gap: compact ? "0.4rem" : "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <span style={{
          position: "absolute", left: 10, fontSize, fontWeight: 700,
          color: "var(--text-tertiary)", pointerEvents: "none",
        }}>¥</span>
        <input
          type="number"
          value={inputValue}
          onChange={(e) => handleInput(e.target.value)}
          onBlur={() => {
            const v = parseFloat(inputValue);
            if (isNaN(v) || v < 1) { setInputValue(String(value / 10000)); }
          }}
          min={1}
          max={10000}
          step={1}
          style={{
            width: compact ? 100 : 130,
            padding: compact ? "0.45rem 0.6rem 0.45rem 1.5rem" : "0.55rem 0.75rem 0.55rem 1.75rem",
            borderRadius: 8,
            border: "2px solid var(--border)",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
            fontSize,
            fontWeight: 700,
            fontFamily: "monospace",
            outline: "none",
          }}
        />
        <span style={{
          position: "absolute", right: 10, fontSize: compact ? "0.75rem" : "0.85rem",
          fontWeight: 600, color: "var(--text-tertiary)", pointerEvents: "none",
        }}>万</span>
      </div>

      <div style={{ display: "flex", gap: "0.3rem" }}>
        {PRESETS.map((p) => (
          <button
            key={p.value}
            onClick={() => handlePreset(p.value)}
            style={{
              padding: btnPad,
              borderRadius: 6,
              border: `1.5px solid ${value === p.value ? "var(--accent)" : "var(--border)"}`,
              background: value === p.value ? "var(--accent-glow)" : "transparent",
              color: value === p.value ? "var(--accent)" : "var(--text-secondary)",
              fontWeight: value === p.value ? 700 : 500,
              fontSize: btnFont,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
