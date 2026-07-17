"""Add an ownership policy for private profile data."""

from collections.abc import Sequence

from alembic import op

revision: str = "003_profile_rls"
down_revision: str | None = "002_alert_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY user_profiles_owner_policy ON user_profiles
        USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_profiles_owner_policy ON user_profiles")
    op.execute("ALTER TABLE user_profiles NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_profiles DISABLE ROW LEVEL SECURITY")
