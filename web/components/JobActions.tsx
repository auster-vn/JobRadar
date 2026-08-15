"use client";

import {BookmarkPlus, ExternalLink, LoaderCircle, Sparkles} from "lucide-react";
import Link from "next/link";
import {useState, type CSSProperties} from "react";

import {ApiError, apiFetch} from "@/lib/client-api";
import type {Application, JobDetail, JobScore} from "@/lib/types";

const scoreParts: Array<{key: keyof JobScore; label: string}> = [
  {key: "skill_score", label: "Kỹ năng"},
  {key: "experience_score", label: "Kinh nghiệm"},
  {key: "location_score", label: "Khu vực"},
];

export function JobActions({job}: {job: JobDetail}) {
  const [score, setScore] = useState<JobScore | null>(null);
  const [busy, setBusy] = useState<"score" | "track" | null>(null);
  const [tracked, setTracked] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function handleFailure(reason: unknown) {
    if (reason instanceof ApiError && reason.status === 401) {
      setNeedsLogin(true);
      setError("Đăng nhập để chấm điểm và theo dõi việc làm này.");
      return;
    }
    if (reason instanceof ApiError && reason.status === 429) {
      setError("Bạn đã dùng hết lượt chấm điểm AI hôm nay. Vui lòng thử lại sau.");
      return;
    }
    if (reason instanceof ApiError && reason.status === 503) {
      setError("Dịch vụ chấm điểm đang tạm gián đoạn. Vui lòng thử lại sau.");
      return;
    }
    setError((reason as Error).message);
  }

  async function calculateScore() {
    setBusy("score");
    setError("");
    setMessage("");
    try {
      setScore(
        await apiFetch<JobScore>(`/api/jobs/${job.id}/score`, {method: "POST"}),
      );
    } catch (reason) {
      handleFailure(reason);
    } finally {
      setBusy(null);
    }
  }

  async function track() {
    setBusy("track");
    setError("");
    setMessage("");
    try {
      await apiFetch<Application>("/api/applications", {
        method: "POST",
        body: JSON.stringify({job_id: job.id, status: "saved"}),
      });
      setTracked(true);
      setMessage("Đã thêm vào danh sách ứng tuyển.");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setTracked(true);
        setMessage("Việc làm này đã có trong danh sách ứng tuyển.");
      } else {
        handleFailure(reason);
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel job-actions-panel" aria-labelledby="job-actions-title">
      <div className="panel-heading">
        <div>
          <h2 id="job-actions-title">Đánh giá cơ hội</h2>
          <p>So sánh với hồ sơ cá nhân và lưu tiến độ ứng tuyển.</p>
        </div>
        <Sparkles size={20} />
      </div>
      <div className="job-cta-grid">
        <button className="primary-button" type="button" onClick={() => void calculateScore()} disabled={busy !== null}>
          {busy === "score" ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
          {busy === "score" ? "Đang chấm điểm..." : "Chấm điểm phù hợp"}
        </button>
        <button className="secondary-button" type="button" onClick={() => void track()} disabled={busy !== null || tracked}>
          {busy === "track" ? <LoaderCircle className="spin" size={17} /> : <BookmarkPlus size={17} />}
          {tracked ? "Đã theo dõi" : busy === "track" ? "Đang lưu..." : "Theo dõi ứng tuyển"}
        </button>
        {job.source_url ? <a className="secondary-button" href={job.source_url} target="_blank" rel="noreferrer"><ExternalLink size={17} />Mở tin gốc</a> : null}
      </div>
      <div className="action-feedback" aria-live="polite">
        {error ? <p className="form-message error" role="alert">{error}</p> : null}
        {message ? <p className="form-message success">{message} <Link href="/applications">Mở danh sách</Link></p> : null}
        {needsLogin ? <Link className="text-button inline-link" href={`/login?next=${encodeURIComponent(`/jobs/${job.id}`)}`}>Đăng nhập hoặc tạo tài khoản</Link> : null}
      </div>
      {score ? (
        <div className="score-result" aria-label={`Điểm phù hợp tổng thể ${Math.round(score.overall_score)} trên 100`}>
          <div className="score-overall">
            <div className="score-ring" style={{"--score": `${Math.max(0, Math.min(100, score.overall_score)) * 3.6}deg`} as CSSProperties}>
              <strong>{Math.round(score.overall_score)}</strong><span>/100</span>
            </div>
            <div><h3>Mức độ phù hợp</h3><p>{score.summary}</p><small>{score.cached ? "Kết quả đã lưu trong bộ nhớ đệm" : "Kết quả mới được tính"}</small></div>
          </div>
          <div className="score-breakdown">
            {scoreParts.map(({key, label}) => {
              const value = Number(score[key]);
              return <div key={key}><span>{label}<b>{Math.round(value)}%</b></span><progress value={value} max="100">{Math.round(value)}%</progress></div>;
            })}
          </div>
          <div className="score-skills">
            <div><strong>Kỹ năng phù hợp</strong><p>{score.matched_skills.length ? score.matched_skills.join(", ") : "Chưa có kỹ năng trùng khớp."}</p></div>
            <div><strong>Kỹ năng nên bổ sung</strong><p>{score.missing_skills.length ? score.missing_skills.join(", ") : "Không có khoảng trống kỹ năng nổi bật."}</p></div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
