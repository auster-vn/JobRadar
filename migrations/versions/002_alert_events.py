"""Add durable alert delivery history."""

from collections.abc import Sequence

from alembic import op

revision: str = "002_alert_events"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alert_events (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          alert_id uuid NOT NULL REFERENCES job_alerts(id) ON DELETE CASCADE,
          job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          channel varchar(20) NOT NULL, status varchar(20) NOT NULL,
          error text, sent_at timestamptz, created_at timestamptz DEFAULT now(),
          CONSTRAINT uq_alert_event_alert_job UNIQUE(alert_id, job_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_alert_events_alert_created ON alert_events(alert_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_events")
