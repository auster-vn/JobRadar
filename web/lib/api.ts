import "server-only";

import type {JobDetail, JobPage, MarketOverview, SalaryBand, SkillDemand} from "./types";

const configuredBase = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL;
const serverBase = (configuredBase ?? "http://localhost:8000").replace(/\/$/, "");

export class ServerApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, revalidate = 60): Promise<T> {
  if (process.env.NODE_ENV === "production" && !configuredBase) {
    throw new ServerApiError(
      500,
      "API_INTERNAL_URL (or NEXT_PUBLIC_API_URL) is required in production.",
    );
  }
  const response = await fetch(`${serverBase}${path}`, {
    next: {revalidate},
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {detail?: string} | null;
    throw new ServerApiError(response.status, body?.detail ?? `API request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getJobs(limit = 8): Promise<JobPage> {
  return request(`/api/jobs?limit=${limit}`);
}

export function getJob(id: string): Promise<JobDetail> {
  return request(`/api/jobs/${encodeURIComponent(id)}`, 300);
}

export function getMarketOverview(): Promise<MarketOverview> {
  return request("/api/analytics/market/overview", 300);
}

export function getSkillDemand(limit = 10): Promise<SkillDemand[]> {
  return request(`/api/analytics/skills/demand?limit=${limit}`, 300);
}

export function getSalaryBands(): Promise<SalaryBand[]> {
  return request("/api/salary/bands", 300);
}
