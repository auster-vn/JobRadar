import {ArrowLeft, Building2, Clock3, MapPin} from "lucide-react";
import type {Metadata} from "next";
import Link from "next/link";
import {notFound} from "next/navigation";

import {JobActions} from "@/components/JobActions";
import {getJob, ServerApiError} from "@/lib/api";
import type {JobDetail} from "@/lib/types";

export const metadata: Metadata = {title: "Chi tiết việc làm"};

function salary(job: JobDetail) {
  if (!job.salary_min && !job.salary_max) return "Thỏa thuận";
  const format = (value: string | null) => value ? `${new Intl.NumberFormat("vi-VN").format(Number(value))} ${job.salary_currency}` : "?";
  return `${format(job.salary_min)} – ${format(job.salary_max)}`;
}

function experience(job: JobDetail) {
  if (job.experience_years_min == null && job.experience_years_max == null) return "Không yêu cầu cụ thể";
  if (job.experience_years_min === job.experience_years_max) return `${job.experience_years_min} năm`;
  return `${job.experience_years_min ?? 0}–${job.experience_years_max ?? "+"} năm`;
}

export default async function JobDetailPage({params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  let job: JobDetail;
  try {
    job = await getJob(id);
  } catch (reason) {
    if (reason instanceof ServerApiError && reason.status === 404) notFound();
    throw reason;
  }

  return (
    <div className="page-stack">
      <Link className="back-link" href="/jobs"><ArrowLeft size={16} />Quay lại danh sách</Link>
      <section className="panel job-detail-hero">
        <span className="company-avatar large"><Building2 size={26} /></span>
        <div><p className="eyebrow">{job.platform}</p><h1>{job.title}</h1><strong>{job.company.name}</strong><div className="job-detail-meta"><span><MapPin size={15} />{job.location.join(", ") || "Việt Nam"}</span><span><Clock3 size={15} />{job.job_type || "Không nêu loại hình"}</span></div></div>
        <div className="job-detail-salary"><span>Mức lương</span><strong>{salary(job)}</strong></div>
      </section>
      <div className="job-detail-layout">
        <article className="panel job-description">
          <h2>Mô tả công việc</h2>
          {job.description ? <p>{job.description}</p> : <div className="inline-empty">Nguồn tuyển dụng chưa cung cấp mô tả chi tiết.</div>}
          <h2>Kỹ năng yêu cầu</h2>
          {job.skills_required.length ? <div className="skill-cloud">{job.skills_required.map((skill) => <span key={skill}>{skill}</span>)}</div> : <div className="inline-empty">Chưa có dữ liệu kỹ năng bắt buộc.</div>}
          {job.skills_nice_to_have.length ? <><h2>Kỹ năng ưu tiên</h2><div className="skill-cloud secondary">{job.skills_nice_to_have.map((skill) => <span key={skill}>{skill}</span>)}</div></> : null}
        </article>
        <aside className="job-detail-side">
          <section className="panel job-facts"><h2>Thông tin chính</h2><dl><div><dt>Cấp độ</dt><dd>{job.job_level || "Không nêu"}</dd></div><div><dt>Kinh nghiệm</dt><dd>{experience(job)}</dd></div><div><dt>Loại công việc</dt><dd>{job.job_type || "Không nêu"}</dd></div><div><dt>Nguồn</dt><dd>{job.platform}</dd></div></dl></section>
          <JobActions job={job} />
        </aside>
      </div>
    </div>
  );
}
