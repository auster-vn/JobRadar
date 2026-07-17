"use client";

import {Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";

const data = [
  {month: "T2", median: 31.2}, {month: "T3", median: 32.4}, {month: "T4", median: 32.1},
  {month: "T5", median: 34.0}, {month: "T6", median: 35.3}, {month: "T7", median: 36.1},
];

export function SalaryTrendChart() {
  return (
    <div className="trend-chart" role="img" aria-label="Xu hướng lương sáu tháng">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{top: 8, right: 8, left: -26, bottom: 0}}>
          <defs><linearGradient id="salaryFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#df6b4f" stopOpacity=".24" /><stop offset="1" stopColor="#df6b4f" stopOpacity="0" /></linearGradient></defs>
          <CartesianGrid stroke="#e8e8e4" vertical={false} />
          <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{fontSize: 11, fill: "#686b67"}} />
          <YAxis domain={[28, 40]} axisLine={false} tickLine={false} tick={{fontSize: 11, fill: "#8b8d89"}} unit="M" />
          <Tooltip contentStyle={{borderRadius: 6, border: "1px solid #dfe2dc", fontSize: 12}} formatter={(value) => [`${value}M`, "Trung vị"]} />
          <Area type="monotone" dataKey="median" stroke="#c94d32" strokeWidth={2.2} fill="url(#salaryFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
