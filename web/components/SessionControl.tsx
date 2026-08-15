"use client";

import {LoaderCircle, LogOut} from "lucide-react";
import Link from "next/link";
import {usePathname, useRouter} from "next/navigation";
import {useCallback, useEffect, useState} from "react";

import {apiFetch} from "@/lib/client-api";

type User = {id: string; email: string};

export function SessionControl() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setUser(await apiFetch<User | null>("/api/auth/session"));
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    window.addEventListener("jobradar:auth-changed", load);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("jobradar:auth-changed", load);
    };
  }, [load]);

  async function logout() {
    setBusy(true);
    setError("");
    try {
      await apiFetch<void>("/api/auth/logout", {method: "POST"});
      setUser(null);
      window.dispatchEvent(new Event("jobradar:auth-changed"));
      router.push("/login");
      router.refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (user === undefined) return <span className="session-placeholder" aria-hidden="true" />;
  if (!user) return <Link className="login-link" href={`/login?next=${encodeURIComponent(pathname)}`}>Đăng nhập</Link>;
  const initials = user.email.slice(0, 2).toUpperCase();
  return <div className="session-control"><Link href="/profile" className="avatar" aria-label={`Hồ sơ ${user.email}`} title={user.email}>{initials}</Link><button className="icon-button session-logout" type="button" disabled={busy} onClick={() => void logout()} aria-label={busy ? "Đang đăng xuất" : "Đăng xuất"} title="Đăng xuất">{busy ? <LoaderCircle className="spin" size={16} /> : <LogOut size={16} />}</button>{error ? <span className="sr-only" role="alert">{error}</span> : null}</div>;
}
