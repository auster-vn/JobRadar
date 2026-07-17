import {ArrowRight, BriefcaseBusiness, Building2, CalendarPlus, TrendingUp, WalletCards} from "lucide-react";
import Link from "next/link";

import {JobRow} from "@/components/JobRow";
import {SalaryTrendChart} from "@/components/SalaryTrendChart";
import {SkillChart} from "@/components/SkillChart";
import {getJobs, getMarketOverview, getSkillDemand} from "@/lib/api";

const number = new Intl.NumberFormat("vi-VN");

export default async function DashboardPage() {
  const [jobs, overview, skills] = await Promise.all([getJobs(6), getMarketOverview(), getSkillDemand(8)]);
  const average = overview.average_salary ? `${Math.round(overview.average_salary / 1_000_000)}M` : "--";
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div><p className="eyebrow">Thứ ba, 14 tháng 7</p><h1>Toàn cảnh thị trường</h1><p>Dữ liệu tuyển dụng công nghệ Việt Nam được tổng hợp và chuẩn hóa.</p></div>
        <Link href="/salary" className="primary-button"><WalletCards size={17} />Kiểm tra mức lương</Link>
      </section>

      <section className="metric-grid" aria-label="Chỉ số thị trường">
        <article className="metric"><span className="metric-icon green"><BriefcaseBusiness size={19} /></span><div><p>Việc làm đang mở</p><strong>{number.format(overview.active_jobs)}</strong><small className="positive"><TrendingUp size={13} /> 8,4% tháng này</small></div></article>
        <article className="metric"><span className="metric-icon coral"><Building2 size={19} /></span><div><p>Doanh nghiệp tuyển dụng</p><strong>{number.format(overview.companies)}</strong><small>Trên toàn quốc</small></div></article>
        <article className="metric"><span className="metric-icon ochre"><CalendarPlus size={19} /></span><div><p>Tin mới tuần này</p><strong>{number.format(overview.new_this_week)}</strong><small className="positive"><TrendingUp size={13} /> 12,1% tuần trước</small></div></article>
        <article className="metric"><span className="metric-icon ink"><WalletCards size={19} /></span><div><p>Lương trung bình</p><strong>{average}</strong><small>VND mỗi tháng</small></div></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel skill-panel"><div className="panel-heading"><div><h2>Kỹ năng được săn đón</h2><p>Số tin yêu cầu kỹ năng trong 90 ngày</p></div><Link href="/market">Chi tiết <ArrowRight size={15} /></Link></div><SkillChart data={skills} /></article>
        <article className="panel trend-panel"><div className="panel-heading"><div><h2>Xu hướng mức lương</h2><p>Trung vị toàn thị trường, triệu VND</p></div><span className="period-chip">6 tháng</span></div><SalaryTrendChart /><div className="trend-summary"><div><span>Hiện tại</span><strong>36,1M</strong></div><div><span>Tăng trưởng</span><strong className="positive">+15,7%</strong></div></div></article>
      </section>

      <section className="panel jobs-panel"><div className="panel-heading"><div><h2>Việc làm mới nhất</h2><p>{number.format(jobs.pagination.total_count)} cơ hội đang hoạt động</p></div><Link href="/jobs">Xem tất cả <ArrowRight size={15} /></Link></div><div className="job-list">{jobs.data.length ? jobs.data.map((job) => <JobRow job={job} key={job.id} />) : <div className="empty-state"><BriefcaseBusiness size={27} /><strong>Chưa có dữ liệu việc làm</strong><span>Bật scraper hoặc chạy seed demo để bắt đầu.</span></div>}</div></section>
    </div>
  );
}
