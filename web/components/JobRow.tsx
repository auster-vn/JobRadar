import {ArrowRight, ArrowUpRight, Building2, Clock3, MapPin} from "lucide-react";
import Link from "next/link";
import type {Job} from "@/lib/types";

function salary(job: Job) {
  if (!job.salary_min && !job.salary_max) return "Thỏa thuận";
  const compact = (value: string | null) => {
    const parsed = Number(value);
    return value && Number.isFinite(parsed) ? `${Math.round(parsed / 1_000_000)}M` : "?";
  };
  return `${compact(job.salary_min)} - ${compact(job.salary_max)}`;
}

function age(value: string | null) {
  if (!value) return "Mới đăng";
  const days = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000));
  return days === 0 ? "Hôm nay" : `${days} ngày trước`;
}

export function JobRow({job}: {job: Job}) {
  return (
    <article className="job-row">
      <div className="company-avatar"><Building2 size={20} /></div>
      <div className="job-main">
        <div className="job-title-line"><Link href={`/jobs/${job.id}`}>{job.title}</Link>{job.platform === "demo" && <span className="demo-label">Demo</span>}</div>
        <span className="company-name">{job.company.name}</span>
        <div className="job-meta"><span><MapPin size={14} />{job.location.join(", ") || "Việt Nam"}</span><span><Clock3 size={14} />{age(job.posted_at)}</span></div>
      </div>
      <div className="job-skills">{job.skills_required.slice(0, 3).map((skill) => <span key={skill}>{skill}</span>)}</div>
      <div className="job-salary"><strong>{salary(job)}</strong><span>/ tháng</span></div>
      <div className="job-actions">
        <Link href={`/jobs/${job.id}`} className="row-action" aria-label={`Xem chi tiết ${job.title}`} title="Xem chi tiết"><ArrowRight size={18} /></Link>
        {job.source_url ? <a href={job.source_url} target="_blank" rel="noreferrer" className="row-action source-action" aria-label={`Mở tin gốc ${job.title}`} title="Mở tin gốc"><ArrowUpRight size={18} /></a> : null}
      </div>
    </article>
  );
}
