"use client";

import {
  BriefcaseBusiness,
  LogOut,
  Save,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, apiFetch } from "@/lib/client-api";
import type { Job } from "@/lib/types";

type User = { id: string; email: string };
type Profile = {
  user_id: string;
  current_title: string | null;
  experience_years: number | null;
  skills: string[];
  current_salary: string | null;
  target_salary: string | null;
  preferred_locations: string[];
  preferred_job_types: string[];
  has_cv: boolean;
};
type Match = {
  job: Job;
  skill_match_pct: number;
  semantic_match_pct: number | null;
  match_score: number;
  matched_skills: string[];
};
const emptyProfile: Profile = {
  user_id: "",
  current_title: null,
  experience_years: null,
  skills: [],
  current_salary: null,
  target_salary: null,
  preferred_locations: [],
  preferred_job_types: [],
  has_cv: false,
};

function csv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProfileWorkspace() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function loadWorkspace() {
    try {
      const me = await apiFetch<User | null>("/api/auth/session");
      if (!me) {
        setUser(null);
        return;
      }
      setUser(me);
      const [current, ranked] = await Promise.all([
        apiFetch<Profile>("/api/profile"),
        apiFetch<Match[]>(
          "/api/profile/matching-jobs?limit=8&min_skill_match_pct=0",
        ),
      ]);
      setProfile(current);
      setMatches(ranked);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401))
        setMessage((error as Error).message);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadWorkspace(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const data = new FormData(event.currentTarget);
    const payload = {
      current_title: String(data.get("current_title") || "") || null,
      experience_years: Number(data.get("experience_years")) || 0,
      skills: csv(String(data.get("skills") || "")),
      current_salary:
        Number(String(data.get("current_salary") || "").replace(/\D/g, "")) ||
        null,
      target_salary:
        Number(String(data.get("target_salary") || "").replace(/\D/g, "")) ||
        null,
      preferred_locations: csv(String(data.get("preferred_locations") || "")),
      preferred_job_types: csv(String(data.get("preferred_job_types") || "")),
    };
    try {
      setProfile(
        await apiFetch<Profile>("/api/profile", {
          method: "PUT",
          body: JSON.stringify(payload),
        }),
      );
      setMatches(
        await apiFetch<Match[]>(
          "/api/profile/matching-jobs?limit=8&min_skill_match_pct=0",
        ),
      );
      setMessage("Đã lưu hồ sơ.");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function uploadCv(file?: File) {
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setMessage("Đang phân tích CV...");
    try {
      setProfile(
        await apiFetch<Profile>("/api/profile/cv", { method: "POST", body }),
      );
      setMessage(
        "Đã phân tích CV và cập nhật kỹ năng. Semantic matching sẽ sẵn sàng sau ít phút.",
      );
      window.setTimeout(() => void loadWorkspace(), 3500);
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function deleteCv() {
    setMessage("");
    try {
      setProfile(
        await apiFetch<Profile>("/api/profile/cv", { method: "DELETE" }),
      );
      setMatches(
        await apiFetch<Match[]>(
          "/api/profile/matching-jobs?limit=8&min_skill_match_pct=0",
        ),
      );
      setMessage("Đã xóa nội dung CV và vector ngữ nghĩa.");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function logout() {
    await apiFetch<void>("/api/auth/logout", { method: "POST" });
    setUser(null);
    setProfile(emptyProfile);
    setMatches([]);
    window.dispatchEvent(new Event("jobradar:auth-changed"));
  }

  if (loading)
    return (
      <section className="panel workspace-state">
        <Sparkles className="spin" size={23} />
        <span>Đang tải hồ sơ...</span>
      </section>
    );
  if (!user)
    return (
      <section className="auth-layout">
        <div className="panel workspace-state">
          <Sparkles size={25} />
          <div className="panel-heading">
            <div>
              <h2>Đăng nhập để mở hồ sơ</h2>
              <p>Dùng hồ sơ riêng để matching và quản lý cảnh báo.</p>
            </div>
          </div>
          {message && <p className="form-message error">{message}</p>}
          <Link className="primary-button" href="/login?next=%2Fprofile">Đăng nhập hoặc tạo tài khoản</Link>
        </div>
      </section>
    );

  return (
    <div className="profile-layout">
      <form className="panel profile-form" onSubmit={saveProfile}>
        <div className="profile-header">
          <div className="profile-avatar">
            {user.email.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h2>{user.email}</h2>
            <p>{profile.current_title || "Chưa đặt chức danh"}</p>
          </div>
          <input
            ref={fileRef}
            type="file"
            hidden
            accept=".pdf,.docx,.txt"
            onChange={(event) => void uploadCv(event.target.files?.[0])}
          />
          <button
            type="button"
            className="secondary-button"
            onClick={() => fileRef.current?.click()}
          >
            <UploadCloud size={17} />
            Tải CV
          </button>
          {profile.has_cv && (
            <button
              type="button"
              className="icon-button"
              title="Xóa dữ liệu CV"
              aria-label="Xóa dữ liệu CV"
              onClick={() => void deleteCv()}
            >
              <Trash2 size={17} />
            </button>
          )}
          <button
            type="button"
            className="icon-button"
            title="Đăng xuất"
            aria-label="Đăng xuất"
            onClick={() => void logout()}
          >
            <LogOut size={17} />
          </button>
        </div>
        <div className="field-row">
          <label className="field">
            <span>Chức danh hiện tại</span>
            <input
              name="current_title"
              defaultValue={profile.current_title ?? ""}
            />
          </label>
          <label className="field">
            <span>Số năm kinh nghiệm</span>
            <input
              name="experience_years"
              type="number"
              defaultValue={profile.experience_years ?? 0}
              min="0"
              max="60"
            />
          </label>
        </div>
        <label className="field">
          <span>Kỹ năng</span>
          <input
            key={profile.skills.join(",")}
            name="skills"
            defaultValue={profile.skills.join(", ")}
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Mức lương hiện tại (VND)</span>
            <input
              name="current_salary"
              inputMode="numeric"
              defaultValue={profile.current_salary ?? ""}
            />
          </label>
          <label className="field">
            <span>Mức lương mục tiêu (VND)</span>
            <input
              name="target_salary"
              inputMode="numeric"
              defaultValue={profile.target_salary ?? ""}
            />
          </label>
        </div>
        <div className="field-row">
          <label className="field">
            <span>Khu vực ưu tiên</span>
            <input
              name="preferred_locations"
              defaultValue={profile.preferred_locations.join(", ")}
            />
          </label>
          <label className="field">
            <span>Loại công việc</span>
            <input
              name="preferred_job_types"
              defaultValue={profile.preferred_job_types.join(", ")}
            />
          </label>
        </div>
        {message && (
          <p
            className={`form-message ${message.startsWith("Đã") ? "success" : ""}`}
          >
            {message}
          </p>
        )}
        <div className="form-actions">
          <button className="primary-button" type="submit">
            <Save size={17} />
            Lưu thay đổi
          </button>
        </div>
      </form>
      <section className="panel matches-panel">
        <div className="panel-heading">
          <div>
            <h2>Việc làm phù hợp</h2>
            <p>Xếp hạng theo kỹ năng và ngữ nghĩa CV</p>
          </div>
          <Sparkles size={19} />
        </div>
        <div className="match-list">
          {matches.length ? (
            matches.map((match) => (
              <a
                className="match-row"
                href={match.job.source_url ?? "#"}
                target="_blank"
                rel="noreferrer"
                key={match.job.id}
              >
                <span className="metric-icon green">
                  <BriefcaseBusiness size={17} />
                </span>
                <div>
                  <strong>
                    {match.job.title_normalized || match.job.title}
                  </strong>
                  <span>
                    {match.job.company.name} ·{" "}
                    {match.matched_skills.slice(0, 3).join(", ") ||
                      "Semantic match"}
                  </span>
                </div>
                <b>{Math.round(match.match_score)}%</b>
              </a>
            ))
          ) : (
            <div className="workspace-state">
              <BriefcaseBusiness size={23} />
              <span>Cập nhật kỹ năng hoặc CV để nhận gợi ý.</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
