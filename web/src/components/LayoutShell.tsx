"use client";

import { usePathname } from "next/navigation";
import AuthGuard from "./AuthGuard";
import Sidebar from "./Sidebar";
import MobileNav from "./MobileNav";

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";

  if (isLoginPage) {
    return <>{children}</>;
  }

  return (
    <AuthGuard>
      {/* Desktop layout */}
      <div className="desktop-layout">
        <Sidebar />
        <main style={{ flex: 1, padding: "1.5rem 2rem", overflow: "auto" }}>
          {children}
        </main>
      </div>

      {/* Mobile layout */}
      <div className="mobile-layout">
        <main style={{ flex: 1, padding: "0.75rem", paddingBottom: 72, overflow: "auto" }}>
          {children}
        </main>
        <MobileNav />
      </div>
    </AuthGuard>
  );
}
