import type {Metadata} from "next";
import {SalaryCalculator} from "@/components/SalaryCalculator";
export const metadata: Metadata = {title: "Mức lương"};
export default function SalaryPage() { return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Salary benchmark</p><h1>Định vị mức lương của bạn</h1><p>Khoảng lương theo vai trò, kinh nghiệm, khu vực và kỹ năng.</p></div></section><SalaryCalculator /></div>; }
