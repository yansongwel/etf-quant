import type { Metadata } from "next";
import "./globals.css";
import LayoutShell from "@/components/LayoutShell";

export const metadata: Metadata = {
  title: "ETF Quant - 量化投研平台",
  description: "中国 ETF 量化投研平台 Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
