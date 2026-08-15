"use client";

import {Bell, BellRing, Clock3, Plus, Trash2, X} from "lucide-react";
import Link from "next/link";
import {FormEvent, useEffect, useState} from "react";

import {ApiError, apiFetch} from "@/lib/client-api";

type Alert = {id: string; name: string; required_skills: string[]; min_salary: string | null; job_levels: string[]; locations: string[]; skill_match_min_pct: string; channel: "email" | "telegram"; is_active: boolean; last_triggered_at: string | null; created_at: string};
type AlertEvent = {id: string; status: string; channel: string; error: string | null; created_at: string};
const split = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

export function AlertManager() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [authorized, setAuthorized] = useState(true);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState<{name: string; events: AlertEvent[]} | null>(null);

  async function load() {
    try { setAlerts(await apiFetch<Alert[]>("/api/alerts")); setAuthorized(true); }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) setAuthorized(false);
      else setError((error as Error).message);
    }
    finally { setLoading(false); }
  }
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    setError(""); setMessage("");
    const salary = Number(String(data.get("min_salary") || "").replace(/\D/g, ""));
    try {
      const created = await apiFetch<Alert>("/api/alerts", {method: "POST", body: JSON.stringify({name: data.get("name"), required_skills: split(String(data.get("skills") || "")), min_salary: salary || null, job_levels: split(String(data.get("levels") || "")), locations: split(String(data.get("locations") || "")), skill_match_min_pct: Number(data.get("match")), channel: data.get("channel"), is_active: true})});
      setAlerts([...alerts, created]); setCreating(false); setMessage("Đã tạo cảnh báo.");
    } catch (reason) { setError((reason as Error).message); }
  }

  async function toggle(alert: Alert) {
    setError("");
    try {
      const updated = await apiFetch<Alert>(`/api/alerts/${alert.id}`, {method: "PUT", body: JSON.stringify({...alert, is_active: !alert.is_active})});
      setAlerts(alerts.map((item) => item.id === alert.id ? updated : item));
    } catch (reason) { setError((reason as Error).message); }
  }
  async function remove(id: string) {
    setError("");
    try { await apiFetch<void>(`/api/alerts/${id}`, {method: "DELETE"}); setAlerts(alerts.filter((item) => item.id !== id)); }
    catch (reason) { setError((reason as Error).message); }
  }
  async function showHistory(alert: Alert) {
    setError("");
    try { const events = await apiFetch<AlertEvent[]>(`/api/alerts/${alert.id}/history`); setHistory({name: alert.name, events}); }
    catch (reason) { setError((reason as Error).message); }
  }

  if (loading) return <section className="panel workspace-state" aria-live="polite"><Clock3 className="spin" size={23} /><span>Đang tải cảnh báo...</span></section>;
  if (!authorized) return <section className="panel workspace-state"><Bell size={25} /><strong>Cần đăng nhập để quản lý cảnh báo</strong><Link className="primary-button" href="/login?next=%2Falerts">Đăng nhập</Link></section>;
  return <><section className="panel alert-panel"><div className="panel-heading"><div><h2>Cảnh báo của bạn</h2><p>Đánh giá tin mới mỗi 30 phút</p></div><button className="primary-button" onClick={() => setCreating(!creating)}>{creating ? <X size={17} /> : <Plus size={17} />}{creating ? "Đóng" : "Tạo cảnh báo"}</button></div>{creating && <form className="alert-create" onSubmit={create}><label className="field"><span>Tên cảnh báo</span><input name="name" required minLength={2} /></label><label className="field"><span>Kỹ năng, cách nhau bằng dấu phẩy</span><input name="skills" placeholder="Python, FastAPI" /></label><div className="field-row"><label className="field"><span>Lương tối thiểu (VND)</span><input name="min_salary" inputMode="numeric" /></label><label className="field"><span>Mức khớp tối thiểu</span><input name="match" type="number" min="0" max="100" defaultValue="60" /></label></div><div className="field-row"><label className="field"><span>Cấp độ</span><input name="levels" placeholder="senior, lead" /></label><label className="field"><span>Khu vực</span><input name="locations" placeholder="Ho Chi Minh, Remote" /></label></div><label className="field"><span>Kênh gửi</span><select name="channel"><option value="email">Email</option><option value="telegram">Telegram</option></select></label><button className="primary-button" type="submit"><Plus size={16} />Lưu cảnh báo</button></form>}{error && <p className="form-message error" role="alert">{error}</p>}{message && <p className="form-message success" aria-live="polite">{message}</p>}<div className="alert-list">{alerts.length ? alerts.map((alert) => <div className="alert-row" key={alert.id}><span className={`metric-icon ${alert.is_active ? "green" : "ink"}`}>{alert.is_active ? <BellRing size={19} /> : <Bell size={19} />}</span><div><strong>{alert.name}</strong><span>{[...alert.required_skills, ...alert.locations].join(" · ") || `Khớp từ ${alert.skill_match_min_pct}%`} · {alert.channel}</span></div><label className="toggle"><input type="checkbox" aria-label={`${alert.is_active ? "Tắt" : "Bật"} cảnh báo ${alert.name}`} checked={alert.is_active} onChange={() => void toggle(alert)} /><span /></label><span className="alert-actions"><button className="icon-button" title="Lịch sử gửi" aria-label={`Lịch sử gửi ${alert.name}`} onClick={() => void showHistory(alert)}><Clock3 size={16} /></button><button className="icon-button" title="Xóa cảnh báo" aria-label={`Xóa cảnh báo ${alert.name}`} onClick={() => void remove(alert.id)}><Trash2 size={16} /></button></span></div>) : !creating && <div className="workspace-state"><Bell size={23} /><span>Chưa có cảnh báo nào.</span></div>}</div></section>{history && <section className="panel history-panel"><div className="panel-heading"><div><h2>Lịch sử: {history.name}</h2><p>100 lần gửi gần nhất</p></div><button className="icon-button" aria-label="Đóng lịch sử" onClick={() => setHistory(null)}><X size={17} /></button></div>{history.events.length ? history.events.map((event) => <div className="history-row" key={event.id}><span>{new Date(event.created_at).toLocaleString("vi-VN")}</span><strong className={event.status === "sent" ? "positive" : "negative"}>{event.status}</strong><span>{event.error || event.channel}</span></div>) : <div className="workspace-state"><Clock3 size={22} /><span>Chưa có lần gửi nào.</span></div>}</section>}</>;
}
