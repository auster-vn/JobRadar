import type {Metadata} from "next";
import {ArrowDownRight, ArrowUpRight} from "lucide-react";
import {SalaryTrendChart} from "@/components/SalaryTrendChart";
import {SkillChart} from "@/components/SkillChart";
import {getSalaryBands, getSkillDemand} from "@/lib/api";
export const metadata: Metadata = {title: "Thị trường"};
export default async function MarketPage() {
  const [skillsResult, bandsResult] = await Promise.allSettled([getSkillDemand(12), getSalaryBands()]);
  const rows = skillsResult.status === "fulfilled" ? skillsResult.value : [];
  const bands = bandsResult.status === "fulfilled" ? bandsResult.value : [];
  const unavailable = skillsResult.status === "rejected" || bandsResult.status === "rejected";
  return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Market intelligence</p><h1>Nhịp đập thị trường</h1><p>Nhu cầu kỹ năng và mặt bằng lương từ dữ liệu đã kiểm chứng.</p></div></section>{unavailable ? <div className="inline-error" role="status">Một phần dữ liệu thị trường tạm thời chưa phản hồi.</div> : null}<section className="dashboard-grid"><article className="panel"><div className="panel-heading"><div><h2>Nhu cầu kỹ năng</h2><p>90 ngày gần nhất</p></div></div><SkillChart data={rows} /></article><article className="panel"><div className="panel-heading"><div><h2>Mặt bằng lương</h2><p>Trung vị theo nhóm vai trò</p></div></div><SalaryTrendChart data={bands} /></article></section><section className="panel market-table"><div className="panel-heading"><div><h2>Xếp hạng kỹ năng</h2><p>Khối lượng tin tuyển dụng và tăng trưởng tháng</p></div></div>{rows.length ? <div className="market-table-scroll"><table><thead><tr><th>Hạng</th><th>Kỹ năng</th><th>Tin tuyển dụng</th><th>Tăng trưởng</th></tr></thead><tbody>{rows.map((row) => <tr key={row.skill}><td>#{row.demand_rank}</td><th scope="row">{row.skill}</th><td>{row.job_count}</td><td><span className={(row.mom_growth_pct ?? 0) >= 0 ? "positive" : "negative"}>{(row.mom_growth_pct ?? 0) >= 0 ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}{Math.abs(row.mom_growth_pct ?? 0)}%</span></td></tr>)}</tbody></table></div> : <div className="workspace-state"><strong>Chưa đủ dữ liệu xếp hạng</strong><span>Bảng sẽ xuất hiện sau khi dữ liệu tuyển dụng được đồng bộ.</span></div>}</section></div>;
}
