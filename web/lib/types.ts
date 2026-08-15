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

export type JobDetail = Job & {
  description: string | null;
  skills_nice_to_have: string[];
  experience_years_min: number | null;
  experience_years_max: number | null;
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
  sources?: string[];
  period_start?: string | null;
  period_end?: string | null;
};

export type JobScore = {
  id: string;
  user_id: string;
  job_id: string;
  overall_score: number;
  skill_score: number;
  experience_score: number;
  location_score: number;
  matched_skills: string[];
  missing_skills: string[];
  summary: string;
  provider: string;
  model_version: string;
  input_hash: string;
  cached: boolean;
  created_at: string;
  updated_at: string;
};

export type ApplicationStatus =
  | "saved"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export type Application = {
  id: string;
  user_id?: string;
  job_id: string;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  job: Job;
};

export type ApplicationPage = {
  data: Application[];
  pagination: {
    limit: number;
    offset: number;
    total_count: number;
    has_more: boolean;
  };
};
