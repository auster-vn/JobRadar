import {ArrowRight, BriefcaseBusiness, Building2, CalendarPlus, WalletCards} from "lucide-react";
import Link from "next/link";

import {JobRow} from "@/components/JobRow";
import {SalaryTrendChart} from "@/components/SalaryTrendChart";
import {SkillChart} from "@/components/SkillChart";
import {getJobs, getMarketOverview, getSalaryBands, getSkillDemand} from "@/lib/api";
import type {JobPage, MarketOverview} from "@/lib/types";

const number = new Intl.NumberFormat("vi-VN");

export default async function DashboardPage() {
  const [jobsResult, overviewResult, skillsResult, bandsResult] = await Promise.allSettled([getJobs(6), getMarketOverview(), getSkillDemand(8), getSalaryBands()]);
  const jobs: JobPage = jobsResult.status === "fulfilled" ? jobsResult.value : {data: [], pagination: {limit: 6, next_cursor: null, has_more: false, total_count: 0}};
  const overview: MarketOverview = overviewResult.status === "fulfilled" ? overviewResult.value : {active_jobs: 0, companies: 0, new_this_week: 0, average_salary: null};
  const skills = skillsResult.status === "fulfilled" ? skillsResult.value : [];
  const bands = bandsResult.status === "fulfilled" ? bandsResult.value : [];
  const unavailable = [jobsResult, overviewResult, skillsResult, bandsResult].filter((result) => result.status === "rejected").length;
  const average = overview.average_salary ? `${Math.round(overview.average_salary / 1_000_000)}M` : "--";
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div><p className="eyebrow">Dữ liệu thị trường</p><h1>Toàn cảnh thị trường</h1><p>Dữ liệu tuyển dụng công nghệ Việt Nam được tổng hợp và chuẩn hóa.</p></div>
        <Link href="/salary" className="primary-button"><WalletCards size={17} />Kiểm tra mức lương</Link>
      </section>

      {unavailable ? <div className="inline-error" role="status">{unavailable} nguồn dữ liệu tạm thời chưa phản hồi. Các khu vực bị ảnh hưởng được hiển thị ở trạng thái trống.</div> : null}
      <section className="metric-grid" aria-label="Chỉ số thị trường">
        <article className="metric"><span className="metric-icon green"><BriefcaseBusiness size={19} /></span><div><p>Việc làm đang mở</p><strong>{number.format(overview.active_jobs)}</strong><small>Tin đang hoạt động</small></div></article>
        <article className="metric"><span className="metric-icon coral"><Building2 size={19} /></span><div><p>Doanh nghiệp tuyển dụng</p><strong>{number.format(overview.companies)}</strong><small>Trên toàn quốc</small></div></article>
        <article className="metric"><span className="metric-icon ochre"><CalendarPlus size={19} /></span><div><p>Tin mới tuần này</p><strong>{number.format(overview.new_this_week)}</strong><small>Trong bảy ngày gần nhất</small></div></article>
        <article className="metric"><span className="metric-icon ink"><WalletCards size={19} /></span><div><p>Lương trung bình</p><strong>{average}</strong><small>VND mỗi tháng</small></div></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel skill-panel"><div className="panel-heading"><div><h2>Kỹ năng được săn đón</h2><p>Số tin yêu cầu kỹ năng trong 90 ngày</p></div><Link href="/market">Chi tiết <ArrowRight size={15} /></Link></div><SkillChart data={skills} /></article>
        <article className="panel trend-panel"><div className="panel-heading"><div><h2>Mặt bằng lương</h2><p>Trung vị theo nhóm vai trò, triệu VND</p></div><span className="period-chip">Dữ liệu công khai</span></div><SalaryTrendChart data={bands} /></article>
      </section>

      <section className="panel jobs-panel"><div className="panel-heading"><div><h2>Việc làm mới nhất</h2><p>{number.format(jobs.pagination.total_count)} cơ hội đang hoạt động</p></div><Link href="/jobs">Xem tất cả <ArrowRight size={15} /></Link></div><div className="job-list">{jobs.data.length ? jobs.data.map((job) => <JobRow job={job} key={job.id} />) : <div className="empty-state"><BriefcaseBusiness size={27} /><strong>Chưa có dữ liệu việc làm</strong><span>Nguồn dữ liệu chưa có tin đang hoạt động.</span></div>}</div></section>
    </div>
  );
}
