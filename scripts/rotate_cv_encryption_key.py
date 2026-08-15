import asyncio
import os

from sqlalchemy import text

from api.core.database import engine


def _read_rotation_keys() -> tuple[str, str]:
    old_key = os.environ.get("OLD_CV_ENCRYPTION_KEY", "")
    new_key = os.environ.get("NEW_CV_ENCRYPTION_KEY", "")
    if len(old_key) < 32 or len(new_key) < 32:
        raise ValueError("both CV rotation keys must contain at least 32 characters")
    if old_key == new_key:
        raise ValueError("the new CV encryption key must differ from the old key")
    return old_key, new_key


async def rotate_cv_encryption_key(old_key: str, new_key: str) -> int:
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL row_security = off"))
        result = await connection.execute(
            text(
                """
                UPDATE user_profiles
                SET cv_text_encrypted = pgp_sym_encrypt(
                  pgp_sym_decrypt(cv_text_encrypted, :old_key),
                  :new_key,
                  'cipher-algo=aes256, compress-algo=1'
                )
                WHERE cv_text_encrypted IS NOT NULL
                """
            ),
            {"old_key": old_key, "new_key": new_key},
        )
        return result.rowcount or 0


async def main() -> None:
    old_key, new_key = _read_rotation_keys()
    rotated = await rotate_cv_encryption_key(old_key, new_key)
    print({"rotated_cv_rows": rotated})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
