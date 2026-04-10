"""
Dataset-level access control shared across all endpoint modules.
"""

from fastapi import HTTPException, status
from app.db.session import get_db_connection

# Role hierarchy: owner > admin > annotator > viewer
_ROLE_RANK = {"owner": 4, "admin": 3, "annotator": 2, "viewer": 1}


def effective_role(dataset_id: str, user_id: int, owner_id: int) -> str | None:
    """Return the caller's effective role on a dataset, or None if no access."""
    if user_id == owner_id:
        return "owner"
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s",
            (dataset_id, user_id),
        )
        row = cursor.fetchone()
        return row["role"] if row else None
    finally:
        conn.close()


def require_role(dataset_id: str, user_id: int, owner_id: int, minimum: str) -> str:
    """Raise 403 unless caller holds at least *minimum* role. Returns effective role."""
    role = effective_role(dataset_id, user_id, owner_id)
    if role is None or _ROLE_RANK.get(role, 0) < _ROLE_RANK.get(minimum, 99):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this dataset",
        )
    return role
