export type Company = {
  id: string;
  name: string;
  logo_url: string | null;
  company_type: string | null;
};

export type Job = {
  id: string;
  title: string;
  title_normalized: string | null;
  company: Company;
  platform: string;
  source_url: string | null;
  job_level: string | null;
  job_type: string | null;
  location: string[];
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string;
  salary_negotiable: boolean;
  skills_required: string[];
  posted_at: string | null;
};

export type JobPage = {
  data: Job[];
  pagination: {limit: number; next_cursor: string | null; has_more: boolean; total_count: number};
};

export type MarketOverview = {
  active_jobs: number;
  companies: number;
  new_this_week: number;
  average_salary: number | null;
};

export type SkillDemand = {
  skill: string;
  job_count: number;
  demand_rank: number;
  mom_growth_pct: number | null;
};

export type SalaryBand = {
  title: string;
  level: string | null;
  location: string | null;
  sample_size: number;
  p25: number;
  median: number;
  p75: number;
  currency: string;
};
