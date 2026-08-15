"use client";

import {Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import type {SkillDemand} from "@/lib/types";

export function SkillChart({data}: {data: SkillDemand[]}) {
  const chartData = data.slice(0, 6);
  if (!chartData.length) return <div className="chart-empty" role="status"><strong>Chưa đủ dữ liệu kỹ năng</strong><span>Biểu đồ sẽ xuất hiện sau khi nguồn việc làm được đồng bộ.</span></div>;
  return (
    <div className="chart-frame" role="img" aria-label="Nhu cầu kỹ năng">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{top: 6, right: 4, left: -24, bottom: 0}}>
          <CartesianGrid stroke="#e8e8e4" vertical={false} />
          <XAxis dataKey="skill" axisLine={false} tickLine={false} tick={{fontSize: 11, fill: "#686b67"}} />
          <YAxis axisLine={false} tickLine={false} tick={{fontSize: 11, fill: "#8b8d89"}} />
          <Tooltip cursor={{fill: "#f1f5f0"}} contentStyle={{borderRadius: 6, border: "1px solid #dfe2dc", fontSize: 12}} />
          <Bar dataKey="job_count" name="Tin tuyển dụng" fill="#176b4d" radius={[3, 3, 0, 0]} maxBarSize={34} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
