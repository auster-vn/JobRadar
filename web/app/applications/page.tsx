import type {Metadata} from "next";

import {ApplicationTracker} from "@/components/ApplicationTracker";

export const metadata: Metadata = {title: "Ứng tuyển"};

export default function ApplicationsPage() {
  return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Application pipeline</p><h1>Theo dõi ứng tuyển</h1><p>Lưu cơ hội và cập nhật từng bước trong quá trình tuyển dụng.</p></div></section><ApplicationTracker /></div>;
}
