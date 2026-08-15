import type {Metadata} from "next";
import {JobsExplorer} from "@/components/JobsExplorer";
import {getJobs} from "@/lib/api";
import type {JobPage} from "@/lib/types";

export const metadata: Metadata = {title: "Việc làm"};
export default async function JobsPage() {
  const heading = <section className="page-heading compact"><div><p className="eyebrow">Khám phá cơ hội</p><h1>Việc làm công nghệ</h1><p>Tin tuyển dụng đã chuẩn hóa theo kỹ năng, mức lương và cấp độ.</p></div></section>;
  let jobs: JobPage = {
    data: [],
    pagination: {limit: 20, next_cursor: null, has_more: false, total_count: 0},
  };
  let initialError = "";
  try {
    jobs = await getJobs(20);
  } catch {
    initialError = "Dịch vụ dữ liệu tạm thời không phản hồi. Hãy thử tìm kiếm lại.";
  }
  return <div className="page-stack">{heading}<JobsExplorer initial={jobs} initialError={initialError} /></div>;
}
