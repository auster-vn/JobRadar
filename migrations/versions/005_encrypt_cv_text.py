"""Encrypt private CV text at rest with pgcrypto."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.core.config import get_settings

revision: str = "005_encrypt_cv_text"
down_revision: str | None = "004_salary_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CIPHER_OPTIONS = "cipher-algo=aes256, compress-algo=1"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.add_column("user_profiles", sa.Column("cv_text_encrypted", sa.LargeBinary()))
    connection = op.get_bind()
    plaintext_rows = connection.scalar(
        sa.text("SELECT count(*) FROM user_profiles WHERE cv_text IS NOT NULL")
    )
    if plaintext_rows:
        key = get_settings().cv_encryption_key
        connection.execute(
            sa.text(
                """
                UPDATE user_profiles
                SET cv_text_encrypted = pgp_sym_encrypt(
                  cv_text, :key, 'cipher-algo=aes256, compress-algo=1'
                )
                WHERE cv_text IS NOT NULL
                """
            ),
            {"key": key},
        )
    op.drop_column("user_profiles", "cv_text")


def downgrade() -> None:
    op.add_column("user_profiles", sa.Column("cv_text", sa.Text()))
    connection = op.get_bind()
    encrypted_rows = connection.scalar(
        sa.text("SELECT count(*) FROM user_profiles WHERE cv_text_encrypted IS NOT NULL")
    )
    if encrypted_rows:
        key = get_settings().cv_encryption_key
        connection.execute(
            sa.text(
                """
                UPDATE user_profiles
                SET cv_text = pgp_sym_decrypt(cv_text_encrypted, :key)
                WHERE cv_text_encrypted IS NOT NULL
                """
            ),
            {"key": key},
        )
    op.drop_column("user_profiles", "cv_text_encrypted")
