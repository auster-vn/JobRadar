import type {Metadata} from "next";
import {ProfileWorkspace} from "@/components/ProfileWorkspace";
export const metadata: Metadata = {title: "Hồ sơ"};
export default function ProfilePage() { return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Hồ sơ nghề nghiệp</p><h1>Thông tin của bạn</h1><p>Dữ liệu dùng riêng cho benchmark và gợi ý việc làm.</p></div></section><ProfileWorkspace /></div>; }
