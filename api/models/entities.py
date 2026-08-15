import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RawJob(Base):
    __tablename__ = "raw_jobs"
    __table_args__ = (
        UniqueConstraint("platform", "platform_job_id", name="uq_raw_job_source_id"),
        Index("ix_raw_jobs_unprocessed", "processed", "scraped_at", postgresql_where=None),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text)


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    industry: Mapped[str | None] = mapped_column(String(160))
    company_size: Mapped[str | None] = mapped_column(String(32))
    company_type: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("platform", "platform_job_id", name="uq_job_source_id"),
        CheckConstraint("salary_min IS NULL OR salary_min > 0", name="ck_job_salary_min"),
        CheckConstraint("salary_max IS NULL OR salary_max > 0", name="ck_job_salary_max"),
        Index("ix_jobs_posted_id", "posted_at", "id"),
        Index("ix_jobs_level_posted", "job_level", "posted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("raw_jobs.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1200))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    title_normalized: Mapped[str | None] = mapped_column(String(300), index=True)
    job_level: Mapped[str | None] = mapped_column(String(32))
    job_type: Mapped[str | None] = mapped_column(String(32))
    location: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    salary_negotiable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    salary_currency: Mapped[str] = mapped_column(String(3), default="VND", server_default="VND")
    description_raw: Mapped[str | None] = mapped_column(Text)
    description_cleaned: Mapped[str | None] = mapped_column(Text)
    skills_required: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    skills_nice_to_have: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    experience_years_min: Mapped[int | None] = mapped_column(Integer)
    experience_years_max: Mapped[int | None] = mapped_column(Integer)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    company: Mapped[Company] = relationship(back_populates="jobs")


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384))
    model_name: Mapped[str] = mapped_column(
        String(200), default="all-MiniLM-L6-v2", server_default="all-MiniLM-L6-v2"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalaryObservation(Base):
    __tablename__ = "salary_observations"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_salary_observation_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    title_normalized: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    job_level: Mapped[str | None] = mapped_column(String(32))
    location: Mapped[str | None] = mapped_column(String(160))
    experience_years_min: Mapped[int | None] = mapped_column(Integer)
    experience_years_max: Mapped[int | None] = mapped_column(Integer)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    category: Mapped[str | None] = mapped_column(String(200))
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_title: Mapped[str | None] = mapped_column(String(300))
    experience_years: Mapped[int | None] = mapped_column(Integer)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    current_salary: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    target_salary: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    preferred_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    preferred_job_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    cv_text_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    cv_storage_path: Mapped[str | None] = mapped_column(String(1000))
    cv_embedding: Mapped[list[float] | None] = mapped_column(VECTOR(384))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_cv(self) -> bool:
        return self.cv_text_encrypted is not None


class JobAlert(Base, TimestampMixin):
    __tablename__ = "job_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), default="Job alert")
    required_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    min_salary: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    job_levels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    skill_match_min_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=60)
    channel: Mapped[str] = mapped_column(String(20), default="email")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("alert_id", "job_id", name="uq_alert_event_alert_job"),
        CheckConstraint("attempt_count >= 0", name="ck_alert_events_attempt_count"),
        Index("ix_alert_events_alert_created", "alert_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_alerts.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScrapeBatch(Base):
    __tablename__ = "scrape_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        CheckConstraint(
            "status IN ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')",
            name="ck_applications_status",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 4000",
            name="ck_applications_notes_length",
        ),
        Index("ix_applications_user_updated", "user_id", "updated_at", "id"),
        Index(
            "ix_applications_user_status",
            "user_id",
            "status",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="saved", server_default="saved")
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job: Mapped[Job] = relationship()


class JobScore(Base, TimestampMixin):
    __tablename__ = "job_scores"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "job_id",
            "provider",
            "model_version",
            "input_hash",
            name="uq_job_scores_cache_key",
        ),
        CheckConstraint(
            "overall_score BETWEEN 0 AND 100",
            name="ck_job_scores_overall_score",
        ),
        CheckConstraint("skill_score BETWEEN 0 AND 100", name="ck_job_scores_skill_score"),
        CheckConstraint(
            "experience_score BETWEEN 0 AND 100",
            name="ck_job_scores_experience_score",
        ),
        CheckConstraint(
            "location_score BETWEEN 0 AND 100",
            name="ck_job_scores_location_score",
        ),
        CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name="ck_job_scores_input_hash",
        ),
        Index("ix_job_scores_user_job_created", "user_id", "job_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    skill_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    experience_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    location_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    missing_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_pipeline_runs_idempotency_key"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')",
            name="ck_pipeline_runs_status",
        ),
        Index("ix_pipeline_runs_kind_created", "kind", "created_at"),
        Index("ix_pipeline_runs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("daily_score_budget >= 0", name="ck_user_settings_score_budget"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    ai_provider: Mapped[str] = mapped_column(
        String(32), default="deterministic", server_default="deterministic"
    )
    ai_model: Mapped[str | None] = mapped_column(String(128))
    daily_score_budget: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    preferences: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'read')",
            name="ck_notifications_status",
        ),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_status", "user_id", "status"),
        Index(
            "uq_notifications_user_job_recommendation",
            "user_id",
            "job_id",
            unique=True,
            postgresql_where=text("kind = 'job_recommendation' AND job_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="in_app", server_default="in_app")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, server_default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(32), default="user", server_default="user")
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
