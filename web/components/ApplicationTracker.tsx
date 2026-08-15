"use client";

import {BriefcaseBusiness, ExternalLink, LoaderCircle, Save} from "lucide-react";
import Link from "next/link";
import {useCallback, useEffect, useState} from "react";

import {ApiError, apiFetch} from "@/lib/client-api";
import type {Application, ApplicationPage, ApplicationStatus} from "@/lib/types";

const statuses: Array<{value: ApplicationStatus; label: string}> = [
  {value: "saved", label: "Đã lưu"},
  {value: "applied", label: "Đã ứng tuyển"},
  {value: "interviewing", label: "Phỏng vấn"},
  {value: "offer", label: "Nhận đề nghị"},
  {value: "rejected", label: "Không phù hợp"},
  {value: "withdrawn", label: "Đã rút"},
];

function ApplicationCard({application, busy, onUpdate}: {
  application: Application;
  busy: boolean;
  onUpdate: (changes: {status?: ApplicationStatus; notes?: string | null}) => Promise<void>;
}) {
  const [notes, setNotes] = useState(application.notes ?? "");
  return (
    <article className="application-card">
      <div className="application-main">
        <span className="metric-icon green"><BriefcaseBusiness size={18} /></span>
        <div>
          <Link href={`/jobs/${application.job_id}`}>{application.job.title}</Link>
          <span>{application.job.company.name} · {application.job.location.join(", ") || "Việt Nam"}</span>
        </div>
        {application.job.source_url ? <a className="row-action" href={application.job.source_url} target="_blank" rel="noreferrer" aria-label={`Mở tin gốc ${application.job.title}`}><ExternalLink size={17} /></a> : null}
      </div>
      <div className="application-fields">
        <label className="field"><span>Trạng thái</span><select value={application.status} disabled={busy} onChange={(event) => void onUpdate({status: event.target.value as ApplicationStatus})}>{statuses.map((status) => <option value={status.value} key={status.value}>{status.label}</option>)}</select></label>
        <label className="field application-notes"><span>Ghi chú</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={4000} placeholder="Lịch phỏng vấn, người liên hệ, bước tiếp theo..." /></label>
        <button className="secondary-button" type="button" disabled={busy || notes === (application.notes ?? "")} onClick={() => void onUpdate({notes: notes || null})}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}Lưu ghi chú</button>
      </div>
      <small>Cập nhật {new Date(application.updated_at).toLocaleDateString("vi-VN")}</small>
    </article>
  );
}

export function ApplicationTracker() {
  const [page, setPage] = useState<ApplicationPage | null>(null);
  const [filter, setFilter] = useState<"all" | ApplicationStatus>("all");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [authorized, setAuthorized] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async (offset = 0, append = false) => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({limit: "20", offset: String(offset)});
    if (filter !== "all") params.set("status", filter);
    try {
      const next = await apiFetch<ApplicationPage>(`/api/applications?${params}`);
      setPage((current) => append && current ? {...next, data: [...current.data, ...next.data]} : next);
      setAuthorized(true);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setAuthorized(false);
      else setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function update(application: Application, changes: {status?: ApplicationStatus; notes?: string | null}) {
    setBusyId(application.id);
    setError("");
    setMessage("");
    try {
      const updated = await apiFetch<Application>(`/api/applications/${application.id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setPage((current) => current ? {...current, data: current.data.map((item) => item.id === updated.id ? updated : item)} : current);
      setMessage("Đã cập nhật tiến độ ứng tuyển.");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (!authorized) return <section className="panel workspace-state"><BriefcaseBusiness size={25} /><strong>Đăng nhập để theo dõi ứng tuyển</strong><span>Danh sách ứng tuyển được lưu riêng cho tài khoản của bạn.</span><Link className="primary-button" href="/login?next=%2Fapplications">Mở trang đăng nhập</Link></section>;

  return (
    <section className="panel applications-panel" aria-busy={loading}>
      <div className="panel-heading applications-heading"><div><h2>Quy trình của bạn</h2><p>{page ? `${page.pagination.total_count} cơ hội đang được theo dõi` : "Đang tải dữ liệu"}</p></div><label className="compact-field"><span>Lọc trạng thái</span><select value={filter} onChange={(event) => setFilter(event.target.value as "all" | ApplicationStatus)}><option value="all">Tất cả</option>{statuses.map((status) => <option value={status.value} key={status.value}>{status.label}</option>)}</select></label></div>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {message ? <p className="form-message success" aria-live="polite">{message}</p> : null}
      {loading && !page ? <div className="workspace-state"><LoaderCircle className="spin" size={24} /><span>Đang tải danh sách ứng tuyển...</span></div> : null}
      {!loading && page?.data.length === 0 ? <div className="workspace-state"><BriefcaseBusiness size={25} /><strong>Chưa có việc làm trong giai đoạn này</strong><span>Mở một việc làm và chọn “Theo dõi ứng tuyển” để bắt đầu.</span><Link className="secondary-button" href="/jobs">Khám phá việc làm</Link></div> : null}
      <div className="application-list">{page?.data.map((application) => <ApplicationCard key={application.id} application={application} busy={busyId === application.id} onUpdate={(changes) => update(application, changes)} />)}</div>
      {page?.pagination.has_more ? <div className="load-more"><button className="secondary-button" type="button" disabled={loading} onClick={() => void load(page.pagination.offset + page.pagination.limit, true)}>{loading ? <LoaderCircle className="spin" size={16} /> : null}{loading ? "Đang tải..." : "Tải thêm"}</button></div> : null}
    </section>
  );
}
