"use client";

import {Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import type {SkillDemand} from "@/lib/types";

const fallback = [
  {skill: "Python", job_count: 184, demand_rank: 1, mom_growth_pct: 12.4},
  {skill: "Java", job_count: 163, demand_rank: 2, mom_growth_pct: 6.8},
  {skill: "React", job_count: 151, demand_rank: 3, mom_growth_pct: 9.2},
  {skill: "AWS", job_count: 124, demand_rank: 4, mom_growth_pct: 14.1},
  {skill: "SQL", job_count: 117, demand_rank: 5, mom_growth_pct: 3.7},
  {skill: "Docker", job_count: 103, demand_rank: 6, mom_growth_pct: 7.4},
];

export function SkillChart({data}: {data: SkillDemand[]}) {
  const chartData = data.length ? data.slice(0, 6) : fallback;
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
