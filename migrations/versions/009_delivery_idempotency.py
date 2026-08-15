"""Make alert retries and recommendation notifications idempotent."""

from collections.abc import Sequence

from alembic import op

revision: str = "009_delivery_idempotency"
down_revision: str | None = "008_saas_domains"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE alert_events ADD COLUMN attempt_count integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE alert_events ADD COLUMN last_attempt_at timestamptz")
    op.execute(
        """
        UPDATE alert_events
        SET attempt_count = 1,
            last_attempt_at = COALESCE(sent_at, created_at, now())
        """
    )
    op.execute(
        """
        ALTER TABLE alert_events
        ADD CONSTRAINT ck_alert_events_attempt_count CHECK (attempt_count >= 0)
        """
    )

    # Revision 008 forces owner RLS. Temporarily restoring the normal owner
    # bypass lets the migration deterministically reconcile all tenants before
    # adding the global partial unique index. PostgreSQL DDL is transactional,
    # so FORCE is restored atomically with the index creation.
    op.execute("ALTER TABLE notifications NO FORCE ROW LEVEL SECURITY")
    op.execute("LOCK TABLE notifications IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY user_id, job_id
                   ORDER BY
                     CASE status
                       WHEN 'read' THEN 0
                       WHEN 'sent' THEN 1
                       WHEN 'pending' THEN 2
                       ELSE 3
                     END,
                     COALESCE(read_at, sent_at, created_at) DESC NULLS LAST,
                     created_at,
                     id
                 ) AS duplicate_rank
          FROM notifications
          WHERE kind = 'job_recommendation' AND job_id IS NOT NULL
        )
        DELETE FROM notifications AS notification
        USING ranked
        WHERE notification.id = ranked.id
          AND ranked.duplicate_rank > 1
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_notifications_user_job_recommendation
        ON notifications(user_id, job_id)
        WHERE kind = 'job_recommendation' AND job_id IS NOT NULL
        """
    )
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_notifications_user_job_recommendation")
    op.execute("ALTER TABLE alert_events DROP CONSTRAINT IF EXISTS ck_alert_events_attempt_count")
    op.execute("ALTER TABLE alert_events DROP COLUMN IF EXISTS last_attempt_at")
    op.execute("ALTER TABLE alert_events DROP COLUMN IF EXISTS attempt_count")
