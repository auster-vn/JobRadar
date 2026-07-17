"use client";

import {Filter, LoaderCircle, Search, SlidersHorizontal} from "lucide-react";
import {FormEvent, useState} from "react";

import {JobRow} from "./JobRow";
import {publicApiBase} from "@/lib/api";
import type {JobPage} from "@/lib/types";

export function JobsExplorer({initial}: {initial: JobPage}) {
  const [page, setPage] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("");
  const [location, setLocation] = useState("");

  async function search(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const params = new URLSearchParams({limit: "20"});
    if (query) params.set("query", query);
    if (level) params.set("level", level);
    if (location) params.set("location", location);
    try {
      const response = await fetch(`${publicApiBase}/api/jobs?${params}`);
      if (!response.ok) throw new Error(`Search failed with status ${response.status}`);
      setPage(await response.json());
    } catch {
      setError("Không thể tải việc làm. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <form className="filter-bar" onSubmit={search}>
        <label className="search-input"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Vai trò, công ty hoặc kỹ năng" /></label>
        <label><span>Cấp độ</span><select value={level} onChange={(event) => setLevel(event.target.value)}><option value="">Tất cả</option><option value="junior">Junior</option><option value="mid">Middle</option><option value="senior">Senior</option><option value="lead">Lead</option></select></label>
        <label><span>Khu vực</span><select value={location} onChange={(event) => setLocation(event.target.value)}><option value="">Toàn quốc</option><option>Ho Chi Minh</option><option>Ha Noi</option><option>Da Nang</option><option>Remote</option></select></label>
        <button className="primary-button" type="submit" disabled={loading}>{loading ? <LoaderCircle className="spin" size={17} /> : <Filter size={17} />}Lọc kết quả</button>
        <button className="icon-button desktop-filter" type="button" aria-label="Bộ lọc nâng cao" title="Bộ lọc nâng cao"><SlidersHorizontal size={18} /></button>
      </form>
      {error ? <div className="inline-error" role="alert">{error}</div> : null}
      <div className="results-heading"><strong>{page.pagination.total_count} việc làm phù hợp</strong><select aria-label="Sắp xếp"><option>Mới nhất</option><option>Lương cao nhất</option></select></div>
      <section className="panel jobs-panel"><div className="job-list">{page.data.length ? page.data.map((job) => <JobRow job={job} key={job.id} />) : <div className="empty-state"><Search size={28} /><strong>Không tìm thấy kết quả</strong><span>Thử thay đổi từ khóa hoặc bộ lọc.</span></div>}</div></section>
    </>
  );
}
