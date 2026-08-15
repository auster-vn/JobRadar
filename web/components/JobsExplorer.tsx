"use client";

import {Filter, LoaderCircle, Search} from "lucide-react";
import {FormEvent, useState} from "react";

import {JobRow} from "./JobRow";
import {apiFetch} from "@/lib/client-api";
import type {JobPage} from "@/lib/types";

export function JobsExplorer({initial, initialError = ""}: {initial: JobPage; initialError?: string}) {
  const [page, setPage] = useState(initial);
  const [loading, setLoading] = useState<"search" | "more" | null>(null);
  const [error, setError] = useState(initialError);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("");
  const [location, setLocation] = useState("");

  function parameters(cursor?: string | null) {
    const params = new URLSearchParams({limit: "20"});
    if (query) params.set("query", query);
    if (level) params.set("level", level);
    if (location) params.set("location", location);
    if (cursor) params.set("cursor", cursor);
    return params;
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    setLoading("search");
    setError("");
    try {
      setPage(await apiFetch<JobPage>(`/api/jobs?${parameters()}`));
    } catch (reason) {
      setError("Không thể tải việc làm. Vui lòng thử lại.");
      console.error(reason);
    } finally {
      setLoading(null);
    }
  }

  async function loadMore() {
    if (!page.pagination.next_cursor) return;
    setLoading("more");
    setError("");
    try {
      const next = await apiFetch<JobPage>(
        `/api/jobs?${parameters(page.pagination.next_cursor)}`,
      );
      setPage({
        data: [...page.data, ...next.data],
        pagination: next.pagination,
      });
    } catch (reason) {
      setError("Không thể tải thêm việc làm. Vui lòng thử lại.");
      console.error(reason);
    } finally {
      setLoading(null);
    }
  }

  return (
    <>
      <form className="filter-bar" onSubmit={search} aria-busy={loading === "search"}>
        <label className="search-input"><span className="sr-only">Vai trò, công ty hoặc kỹ năng</span><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Vai trò, công ty hoặc kỹ năng" /></label>
        <label><span>Cấp độ</span><select value={level} onChange={(event) => setLevel(event.target.value)}><option value="">Tất cả</option><option value="junior">Junior</option><option value="mid">Middle</option><option value="senior">Senior</option><option value="lead">Lead</option></select></label>
        <label><span>Khu vực</span><select value={location} onChange={(event) => setLocation(event.target.value)}><option value="">Toàn quốc</option><option>Ho Chi Minh</option><option>Ha Noi</option><option>Da Nang</option><option>Remote</option></select></label>
        <button className="primary-button" type="submit" disabled={loading !== null}>{loading === "search" ? <LoaderCircle className="spin" size={17} /> : <Filter size={17} />}Lọc kết quả</button>
      </form>
      {error ? <div className="inline-error" role="alert">{error}</div> : null}
      <div className="results-heading" aria-live="polite"><strong>{page.pagination.total_count} việc làm phù hợp</strong><span>Mới nhất trước</span></div>
      <section className="panel jobs-panel"><div className="job-list">{page.data.length ? page.data.map((job) => <JobRow job={job} key={job.id} />) : <div className="empty-state"><Search size={28} /><strong>Không tìm thấy kết quả</strong><span>Thử thay đổi từ khóa hoặc bộ lọc.</span></div>}</div></section>
      {page.pagination.has_more ? <div className="load-more"><button className="secondary-button" type="button" onClick={() => void loadMore()} disabled={loading !== null}>{loading === "more" ? <LoaderCircle className="spin" size={17} /> : null}{loading === "more" ? "Đang tải..." : "Tải thêm việc làm"}</button></div> : null}
    </>
  );
}
