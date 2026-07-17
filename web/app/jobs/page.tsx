import type {Metadata} from "next";
import {JobsExplorer} from "@/components/JobsExplorer";
import {getJobs} from "@/lib/api";

export const metadata: Metadata = {title: "Việc làm"};
export default async function JobsPage() {
  const jobs = await getJobs(20);
  return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Khám phá cơ hội</p><h1>Việc làm công nghệ</h1><p>Tin tuyển dụng đã chuẩn hóa theo kỹ năng, mức lương và cấp độ.</p></div></section><JobsExplorer initial={jobs} /></div>;
}
