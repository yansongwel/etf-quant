"use client";

import { AnimatedCharacters } from "@/components/AnimatedCharacters";
import { useState, type FormEvent } from "react";
import styles from "./login.module.css";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

async function verifyApiKey(key: string): Promise<boolean> {
  try {
    const res = await fetch("/health");
    if (!res.ok) return false;
    // If API is reachable, verify the key by hitting a protected endpoint
    const check = await fetch("/api/portfolio/list", {
      headers: key ? { "X-API-Key": key } : {},
    });
    return check.ok;
  } catch {
    return false;
  }
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [passwordValue, setPasswordValue] = useState("");
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState(API_KEY);
  const [username, setUsername] = useState("");

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("请输入用户名");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const valid = await verifyApiKey(apiKey);
      if (valid) {
        localStorage.setItem("etf_quant_user", username);
        if (apiKey) localStorage.setItem("etf_quant_api_key", apiKey);
        localStorage.setItem("etf_quant_logged_in", "true");
        window.location.href = "/";
      } else {
        setError("API 连接失败，请检查后端服务是否运行");
      }
    } catch {
      setError("登录失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      {/* Left: Brand + Animation */}
      <div className={styles.leftPanel}>
        <div className={styles.leftTop}>
          <div className={styles.brandMark}>
            <span className={styles.brandIcon}>EQ</span>
          </div>
          <span className={styles.brandName}>ETF Quant</span>
        </div>

        <div className={styles.charactersArea}>
          <AnimatedCharacters
            isTyping={isTyping}
            showPassword={showPassword}
            passwordLength={passwordValue.length}
          />
        </div>

        <div className={styles.leftFooter}>
          <span>A 股 ETF 量化投研平台</span>
        </div>

        <div className={styles.decorBlur1} />
        <div className={styles.decorBlur2} />
        <div className={styles.decorGrid} />
      </div>

      {/* Right: Login Form */}
      <div className={styles.rightPanel}>
        <div className={styles.formWrapper}>
          <div className={styles.mobileLogo}>
            <div className={styles.mobileLogoIcon}>EQ</div>
            <span>ETF Quant</span>
          </div>

          <div className={styles.formHeader}>
            <h1 className={styles.formTitle}>登录量化看板</h1>
            <p className={styles.formSubtitle}>
              实时信号 · 板块轮动 · 持仓管理
            </p>
          </div>

          <form onSubmit={handleLogin} className={styles.form}>
            <div className={styles.fieldLabel}>用户名</div>
            <div className={styles.inputWrapper}>
              <svg className={styles.inputIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <input
                type="text"
                placeholder="输入用户名"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onFocus={() => setIsTyping(true)}
                onBlur={() => setIsTyping(false)}
                className={styles.input}
                autoComplete="username"
              />
            </div>

            <div className={styles.fieldLabel}>API Key（可选）</div>
            <div className={styles.inputWrapper}>
              <svg className={styles.inputIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <input
                type={showPassword ? "text" : "password"}
                placeholder="写入操作需要 API Key"
                value={passwordValue}
                onChange={(e) => {
                  setPasswordValue(e.target.value);
                  setApiKey(e.target.value);
                }}
                className={styles.input}
                autoComplete="current-password"
              />
              <button
                type="button"
                className={styles.eyeToggle}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                )}
              </button>
            </div>

            {error && <div className={styles.errorBox}>{error}</div>}

            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? "连接中..." : "进入看板"}
            </button>
          </form>

          <div className={styles.hint}>
            无需注册 · 输入任意用户名即可进入<br />
            API Key 仅用于写入操作（添加持仓等）
          </div>
        </div>
      </div>
    </div>
  );
}
