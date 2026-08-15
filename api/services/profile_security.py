import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings


async def set_profile_owner(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def store_cv_text(session: AsyncSession, user_id: uuid.UUID, plaintext: str) -> None:
    result = await session.execute(
        text(
            """
            UPDATE user_profiles
            SET cv_text_encrypted = pgp_sym_encrypt(
              :plaintext, :key, 'cipher-algo=aes256, compress-algo=1'
            )
            WHERE user_id = :user_id
            RETURNING user_id
            """
        ),
        {
            "plaintext": plaintext,
            "key": get_settings().cv_encryption_key,
            "user_id": str(user_id),
        },
    )
    if result.scalar_one_or_none() is None:
        raise RuntimeError("profile row unavailable for encrypted CV storage")


async def load_cv_text(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    value = await session.scalar(
        text(
            """
            SELECT pgp_sym_decrypt(cv_text_encrypted, :key)
            FROM user_profiles
            WHERE user_id = :user_id AND cv_text_encrypted IS NOT NULL
            """
        ),
        {"key": get_settings().cv_encryption_key, "user_id": str(user_id)},
    )
    if value is not None and not isinstance(value, str):
        raise TypeError("decrypted CV payload is not text")
    return value
