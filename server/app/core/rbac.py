"""
RBAC (Role-Based Access Control) System
Handles authentication, authorization, and role management
"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
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
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission"""
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms


def get_role_permissions(role: str) -> List[str]:
    """Get all permissions for a role"""
    return ROLE_PERMISSIONS.get(role, [])

