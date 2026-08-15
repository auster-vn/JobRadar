"use client";

import {LoaderCircle, LogIn, UserPlus} from "lucide-react";
import {useRouter} from "next/navigation";
import {FormEvent, useEffect, useState} from "react";

import {ApiError, apiFetch} from "@/lib/client-api";

type User = {id: string; email: string};

export function AuthPanel({nextPath}: {nextPath: string}) {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void apiFetch<User | null>("/api/auth/session")
      .then((user) => {
        if (active && user) router.replace(nextPath);
      })
      .catch((reason) => {
        if (!(reason instanceof ApiError && reason.status === 401)) console.error(reason);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [nextPath, router]);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await apiFetch(`/api/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({email: data.get("email"), password: data.get("password")}),
      });
      window.dispatchEvent(new Event("jobradar:auth-changed"));
      router.replace(nextPath);
      router.refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (checking) return <section className="panel workspace-state" aria-live="polite"><LoaderCircle className="spin" size={23} /><span>Đang kiểm tra phiên đăng nhập...</span></section>;

  return (
    <form className="panel auth-form" onSubmit={authenticate} aria-busy={busy}>
      <div className="panel-heading"><div><h2>{mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}</h2><p>Dùng hồ sơ riêng để chấm điểm việc làm và quản lý ứng tuyển.</p></div>{mode === "login" ? <LogIn size={20} /> : <UserPlus size={20} />}</div>
      <label className="field"><span>Email</span><input name="email" type="email" required autoComplete="email" autoFocus /></label>
      <label className="field"><span>Mật khẩu</span><input name="password" type="password" minLength={mode === "register" ? 10 : 1} required autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      <button className="primary-button wide" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : mode === "login" ? <LogIn size={17} /> : <UserPlus size={17} />}{busy ? "Đang xử lý..." : mode === "login" ? "Đăng nhập" : "Đăng ký"}</button>
      <button className="text-button" type="button" disabled={busy} onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}</button>
    </form>
  );
}
