import {SearchX} from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return <section className="panel workspace-state"><SearchX size={28} /><h1>Không tìm thấy nội dung</h1><span>Việc làm có thể đã đóng hoặc đường dẫn không còn hợp lệ.</span><Link className="primary-button" href="/jobs">Xem việc làm đang mở</Link></section>;
}
