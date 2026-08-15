import {LoaderCircle} from "lucide-react";

export default function Loading() {
  return <section className="panel workspace-state" aria-live="polite"><LoaderCircle className="spin" size={24} /><span>Đang tải dữ liệu...</span></section>;
}
