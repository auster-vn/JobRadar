"use client";

import { Calculator, MapPin, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import { apiFetch } from "@/lib/client-api";

type Result = {
  salary_estimate: number;
  salary_p25: number;
  salary_p75: number;
  sample_size: number;
  currency: string;
  source: string;
  sources: string[];
  period_end: string | null;
};
const millions = (value: number) => `${Math.round(value / 100_000) / 10}M`;
const monthYear = (date: string) => {
  const [year, month] = date.split("-");
  return `${month}/${year}`;
};

export function SalaryCalculator() {
  const [experience, setExperience] = useState(4);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      setResult(
        await apiFetch<Result>("/api/salary/predict", {
          method: "POST",
          body: JSON.stringify({
            title: data.get("title"),
            level: data.get("level"),
            location: data.get("location"),
            experience_years: experience,
            skills: String(data.get("skills") || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          }),
        }),
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="salary-layout">
      <form className="panel calculator-panel" onSubmit={calculate}>
        <div className="panel-heading">
          <div>
            <h2>Thông tin vị trí</h2>
            <p>So sánh theo nguồn và kỳ quan sát đã kiểm chứng</p>
          </div>
          <Calculator size={20} />
        </div>
        <label className="field">
          <span>Chức danh</span>
          <select name="title" defaultValue="Backend Developer">
            <option>Backend Developer</option>
            <option>Frontend Developer</option>
            <option>Data Engineer</option>
            <option>DevOps Engineer</option>
            <option>ML Engineer</option>
          </select>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Cấp độ</span>
            <select name="level" defaultValue="mid">
              <option value="junior">Junior</option>
              <option value="mid">Middle</option>
              <option value="senior">Senior</option>
              <option value="lead">Lead</option>
            </select>
          </label>
          <label className="field">
            <span>Khu vực</span>
            <span className="input-with-icon">
              <MapPin size={16} />
              <select name="location" defaultValue="Ho Chi Minh">
                <option>Ho Chi Minh</option>
                <option>Ha Noi</option>
                <option>Da Nang</option>
                <option>Remote</option>
              </select>
            </span>
          </label>
        </div>
        <label className="field range-field">
          <span>
            Kinh nghiệm <b>{experience} năm</b>
          </span>
          <input
            type="range"
            min="0"
            max="12"
            value={experience}
            onChange={(event) => setExperience(Number(event.target.value))}
          />
        </label>
        <label className="field">
          <span>Kỹ năng chính</span>
          <input name="skills" defaultValue="Python, FastAPI, PostgreSQL" />
        </label>
        {error && <p className="form-message error">{error}</p>}
        <button
          className="primary-button wide"
          type="submit"
          disabled={loading}
        >
          <Sparkles className={loading ? "spin" : ""} size={17} />
          {loading ? "Đang tính..." : "Tính mức lương thị trường"}
        </button>
      </form>
      <section className="panel salary-result" aria-live="polite">
        {result ? (
          <>
            <p>Mức lương ước tính</p>
            <div className="salary-number">
              <strong>{millions(result.salary_estimate)}</strong>
              <span>{result.currency} / tháng</span>
            </div>
            <div className="salary-scale">
              <span style={{ left: "30%" }} />
              <i style={{ left: "52%" }} />
            </div>
            <div className="salary-range">
              <div>
                <span>P25</span>
                <strong>{millions(result.salary_p25)}</strong>
              </div>
              <div>
                <span>Trung vị</span>
                <strong>{millions(result.salary_estimate)}</strong>
              </div>
              <div>
                <span>P75</span>
                <strong>{millions(result.salary_p75)}</strong>
              </div>
            </div>
            <small>
              {result.source === "market_quantiles"
                ? `Dựa trên ${result.sample_size} quan sát công khai${result.period_end ? `, cập nhật đến ${monthYear(result.period_end)}` : ""}.`
                : `Ước tính cold-start; hiện chỉ có ${result.sample_size} mẫu so sánh phù hợp.`}
            </small>
          </>
        ) : (
          <div className="result-placeholder">
            <Calculator size={34} />
            <strong>Kết quả benchmark</strong>
            <span>Điền thông tin để xem khoảng lương phù hợp.</span>
          </div>
        )}
      </section>
    </div>
  );
}
