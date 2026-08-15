"use client";

import {Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";

import type {SalaryBand} from "@/lib/types";

export function SalaryTrendChart({data}: {data: SalaryBand[]}) {
  const chartData = data.slice(0, 6).map((band) => ({
    label: band.title.length > 14 ? `${band.title.slice(0, 12)}…` : band.title,
    median: Math.round(band.median / 100_000) / 10,
    sample_size: band.sample_size,
  }));
  if (!chartData.length) return <div className="chart-empty" role="status"><strong>Chưa đủ dữ liệu lương</strong><span>Cần ít nhất ba quan sát công khai cho mỗi phân khúc.</span></div>;
  return (
    <div className="trend-chart" role="img" aria-label="Mức lương trung vị theo nhóm vai trò">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{top: 8, right: 8, left: -20, bottom: 0}}>
          <CartesianGrid stroke="#e8e8e4" vertical={false} />
          <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{fontSize: 10, fill: "#686b67"}} />
          <YAxis axisLine={false} tickLine={false} tick={{fontSize: 11, fill: "#8b8d89"}} unit="M" />
          <Tooltip contentStyle={{borderRadius: 6, border: "1px solid #dfe2dc", fontSize: 12}} formatter={(value) => [`${value}M`, "Trung vị"]} />
          <Bar dataKey="median" name="Lương trung vị" fill="#c94d32" radius={[3, 3, 0, 0]} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
