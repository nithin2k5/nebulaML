"""
RBAC (Role-Based Access Control) System
Handles authentication, authorization, and role management
"""

import jwt
import bcrypt
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # No known-value fallback: a hardcoded default would let anyone who has
    # read this file forge valid tokens against a deployment that forgot to
    # set SECRET_KEY. A random per-process secret fails closed instead -
    # existing tokens/deployments must set SECRET_KEY explicitly to persist
    # sessions across restarts.
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning(
        "SECRET_KEY is not set in the environment. Using a randomly generated "
        "key for this process only; all existing tokens will be invalidated "
        "on restart. Set SECRET_KEY before deploying to production."
    )
ALGORITHM = "HS256"

# Access tokens live in the browser (localStorage today), so anything that can
# read them — XSS, a leaked log line, a shared device — gets the full window.
# The default used to be 10080 minutes: a stolen token was good for seven days.
# It is now an hour, with a separately-tracked refresh token carrying the long
# session so the user is not re-prompted hourly.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Tokens are stamped with their purpose. Invite tokens (collaboration.py) are
# signed with the same secret and algorithm, so without a type claim the only
# thing keeping one from being presented as the other is which fields each
# payload happens to carry — a latent token-confusion bug waiting on the next
# field someone adds.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_CLAIM = "typ"
BCRYPT_ROUNDS = 12  # Increased for production-grade security

# Cache for password hashes (optional, for even faster repeated logins)
_password_cache = {}

# Role definitions
class Role:
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    
# Permission definitions
class Permission:
    # Dataset permissions
    CREATE_DATASET = "create_dataset"
    VIEW_DATASET = "view_dataset"
    EDIT_DATASET = "edit_dataset"
    DELETE_DATASET = "delete_dataset"
    
    # Training permissions
    START_TRAINING = "start_training"
    VIEW_TRAINING = "view_training"
    STOP_TRAINING = "stop_training"
    
    # Model permissions
    UPLOAD_MODEL = "upload_model"
    VIEW_MODEL = "view_model"
    DELETE_MODEL = "delete_model"
    
    # Inference permissions
    RUN_INFERENCE = "run_inference"
    VIEW_INFERENCE = "view_inference"
    
    # System permissions
    MANAGE_USERS = "manage_users"
    VIEW_LOGS = "view_logs"
    SYSTEM_CONFIG = "system_config"

# Role-Permission mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        # Full access to everything
        Permission.CREATE_DATASET,
        Permission.VIEW_DATASET,
        Permission.EDIT_DATASET,
        Permission.DELETE_DATASET,
        Permission.START_TRAINING,
        Permission.VIEW_TRAINING,
        Permission.STOP_TRAINING,
        Permission.UPLOAD_MODEL,
        Permission.VIEW_MODEL,
        Permission.DELETE_MODEL,
        Permission.RUN_INFERENCE,
        Permission.VIEW_INFERENCE,
        Permission.MANAGE_USERS,
        Permission.VIEW_LOGS,
        Permission.SYSTEM_CONFIG,
    ],
    Role.USER: [
        # Standard user access
        Permission.CREATE_DATASET,
        Permission.VIEW_DATASET,
        Permission.EDIT_DATASET,
        Permission.DELETE_DATASET,
        Permission.START_TRAINING,
        Permission.VIEW_TRAINING,
        Permission.STOP_TRAINING,
        Permission.UPLOAD_MODEL,
        Permission.VIEW_MODEL,
        Permission.DELETE_MODEL,
        Permission.RUN_INFERENCE,
        Permission.VIEW_INFERENCE,
    ],
    Role.VIEWER: [
        # Read-only access
        Permission.VIEW_DATASET,
        Permission.VIEW_TRAINING,
        Permission.VIEW_MODEL,
        Permission.VIEW_INFERENCE,
    ]
}


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with optimized rounds"""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, TOKEN_TYPE_CLAIM: TOKEN_TYPE_ACCESS})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, jti: str) -> str:
    """Create a refresh token bound to a server-side row via `jti`.

    The jti is what makes rotation enforceable: the server can revoke one
    specific refresh token, which a stateless JWT alone cannot express.
    """
    payload = {
        "user_id": user_id,
        "jti": jti,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        TOKEN_TYPE_CLAIM: TOKEN_TYPE_REFRESH,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str, expected_type: Optional[str]) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        # Covers ExpiredSignatureError, bad signature and malformed input.
        return None

    if expected_type is None:
        return payload

    actual = payload.get(TOKEN_TYPE_CLAIM)
    if actual == expected_type:
        return payload
    # Tokens minted before this claim existed carry no `typ`. Accept them as
    # access tokens so a deploy does not sign everyone out mid-session.
    # TODO: drop this fallback once ACCESS_TOKEN_EXPIRE_MINUTES has elapsed
    # past the deploy (and definitely before REFRESH_TOKEN_EXPIRE_DAYS).
    if actual is None and expected_type == TOKEN_TYPE_ACCESS:
        return payload
    logger.warning(
        "Rejected token: expected typ=%s, got typ=%s", expected_type, actual
    )
    return None


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify an access token. Rejects refresh and invite tokens."""
    return _decode(token, TOKEN_TYPE_ACCESS)


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode and verify a refresh token. Rejects access and invite tokens."""
    return _decode(token, TOKEN_TYPE_REFRESH)


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission"""
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms


def get_role_permissions(role: str) -> List[str]:
    """Get all permissions for a role"""
    return ROLE_PERMISSIONS.get(role, [])

