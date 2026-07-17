import type {JobPage, MarketOverview, SalaryBand, SkillDemand} from "./types";

const serverBase = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const publicApiBase = "";

async function request<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${serverBase}${path}`, {cache: "no-store"});
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export function getJobs(limit = 8): Promise<JobPage> {
  return request(`/api/jobs?limit=${limit}`, {
    data: [],
    pagination: {limit, next_cursor: null, has_more: false, total_count: 0},
  });
}

export function getMarketOverview(): Promise<MarketOverview> {
  return request("/api/analytics/market/overview", {
    active_jobs: 0,
    companies: 0,
    new_this_week: 0,
    average_salary: null,
  });
}

export function getSkillDemand(limit = 10): Promise<SkillDemand[]> {
  return request(`/api/analytics/skills/demand?limit=${limit}`, []);
}

export function getSalaryBands(): Promise<SalaryBand[]> {
  return request("/api/salary/bands", []);
}
