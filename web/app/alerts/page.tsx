import type {Metadata} from "next";
import {AlertManager} from "@/components/AlertManager";
export const metadata: Metadata = {title: "Thông báo"};
export default function AlertsPage() { return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Theo dõi chủ động</p><h1>Cảnh báo việc làm</h1><p>Nhận thông báo khi có cơ hội khớp chính xác với tiêu chí.</p></div></section><AlertManager /></div>; }
