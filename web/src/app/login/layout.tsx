import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "登录 - ETF Quant",
  description: "ETF Quant 量化投研平台登录",
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
