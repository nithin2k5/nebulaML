"""Server-side state for refresh-token rotation.

A JWT on its own cannot be revoked — that is the whole point of it being
stateless. Rotation needs a server-side record per token so a single refresh
token can be retired the moment it is used, which is what turns theft from
"valid until expiry" into "detectable on second use".

The flow:

  login    → issue access + refresh, insert a row for the refresh jti
  refresh  → validate jti is live, revoke it, issue a fresh pair
  reuse    → an already-revoked jti comes back: either an attacker replaying a
             stolen token or the legitimate client replaying after the attacker
             already rotated it. Which one cannot be distinguished, so revoke
             every token for that user and force a re-login.
  logout   → revoke the presented token's family
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from mysql.connector import Error

from app.core.logging import logger
from app.db.session import db_cursor


class RefreshTokenService:
    @staticmethod
    def issue(user_id: int, ttl_days: int) -> str:
        """Record a new refresh token and return its jti."""
        jti = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO refresh_tokens (jti, user_id, expires_at) VALUES (%s, %s, %s)",
                (jti, user_id, expires_at.replace(tzinfo=None)),
            )
        return jti

    @staticmethod
    def get(jti: str) -> Optional[dict]:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT jti, user_id, expires_at, revoked_at FROM refresh_tokens WHERE jti = %s",
                (jti,),
            )
            return cursor.fetchone()

    @staticmethod
    def revoke(jti: str) -> None:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE refresh_tokens SET revoked_at = UTC_TIMESTAMP() "
                "WHERE jti = %s AND revoked_at IS NULL",
                (jti,),
            )

    @staticmethod
    def revoke_all_for_user(user_id: int) -> int:
        """Revoke every live refresh token for a user. Returns the row count."""
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE refresh_tokens SET revoked_at = UTC_TIMESTAMP() "
                "WHERE user_id = %s AND revoked_at IS NULL",
                (user_id,),
            )
            return cursor.rowcount

    @staticmethod
    def rotate(jti: str, user_id: int, ttl_days: int) -> Optional[str]:
        """Consume `jti` and issue its replacement.

        Returns the new jti, or None if the presented token is not usable —
        unknown, expired, or already revoked. A revoked-but-known jti is treated
        as a reuse attempt and takes the user's whole token family down with it.
        """
        row = RefreshTokenService.get(jti)
        if row is None:
            logger.warning("Refresh rejected: unknown jti for user %s", user_id)
            return None

        if row["user_id"] != user_id:
            # The signature was valid but the claim disagrees with the record.
            logger.error("Refresh rejected: jti %s does not belong to user %s", jti, user_id)
            return None

        if row["revoked_at"] is not None:
            logger.error(
                "Refresh token reuse detected for user %s (jti %s). "
                "Revoking all refresh tokens for this user.",
                user_id,
                jti,
            )
            RefreshTokenService.revoke_all_for_user(user_id)
            return None

        if row["expires_at"] < datetime.now(timezone.utc).replace(tzinfo=None):
            logger.info("Refresh rejected: jti %s expired", jti)
            return None

        RefreshTokenService.revoke(jti)
        return RefreshTokenService.issue(user_id, ttl_days)

    @staticmethod
    def purge_expired() -> int:
        """Delete rows past expiry. Safe to call on a schedule."""
        try:
            with db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM refresh_tokens WHERE expires_at < UTC_TIMESTAMP()")
                return cursor.rowcount
        except (Error, RuntimeError) as e:
            logger.warning(f"Could not purge expired refresh tokens: {e}")
            return 0
