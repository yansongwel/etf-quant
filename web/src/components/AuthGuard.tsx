"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setAuthed(true);
      setChecked(true);
      return;
    }
    const loggedIn = localStorage.getItem("etf_quant_logged_in") === "true";
    if (!loggedIn) {
      window.location.href = "/login";
      return;
    }
    setAuthed(true);
    setChecked(true);
  }, [pathname]);

  if (!checked) return null;
  if (!authed) return null;
  return <>{children}</>;
}
