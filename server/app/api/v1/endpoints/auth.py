"""
Authentication routes for login, register, and user management
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
import mysql.connector
from app.db.session import get_db_connection
from app.core.rbac import (
    hash_password, 
    verify_password, 
    create_access_token, 
    decode_access_token,
    Role,
    Permission,
    has_permission,
    get_role_permissions
)
import uuid
import random
from datetime import datetime, timedelta
from app.core.email import send_otp_email

router = APIRouter()
security = HTTPBearer()


# Pydantic models
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    role: Optional[str] = Role.USER


class UserLogin(BaseModel):
    email: str

class UserVerify(BaseModel):
    email: str
    otp: str

class EmailRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


# Dependency to get current user from token
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user"""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Get user from database
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user: {str(e)}"
        )


# Dependency to check permissions
def require_permission(permission: str):
    """Decorator to require specific permission"""
    async def permission_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission}"
            )
        return current_user
    return permission_checker


@router.post("/register")
async def register(user_data: UserRegister):
    """Register a new user"""
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = %s UNION SELECT id FROM pending_registrations WHERE username = %s", (user_data.username, user_data.username))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        
        # Check if email exists in users table
        cursor.execute("SELECT id FROM users WHERE email = %s", (user_data.email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        
        # Generate OTP
        otp_code = f"{random.randint(100000, 999999)}"
        otp_expiry = datetime.now() + timedelta(minutes=10)
        
        # Check if email exists in pending, update or insert
        cursor.execute("SELECT id FROM pending_registrations WHERE email = %s", (user_data.email,))
        pending_user = cursor.fetchone()
        
        if pending_user:
            cursor.execute(
                """
                UPDATE pending_registrations 
                SET username = %s, role = %s, verification_code = %s, verification_code_expires = %s
                WHERE id = %s
                """,
                (user_data.username, user_data.role, otp_code, otp_expiry, pending_user['id'])
            )
        else:
            cursor.execute(
                """
                INSERT INTO pending_registrations (username, email, role, verification_code, verification_code_expires)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_data.username, user_data.email, user_data.role, otp_code, otp_expiry)
            )
        connection.commit()
        
        cursor.close()
        connection.close()
        
        # Send Email
        send_otp_email(user_data.email, otp_code)
        
        # Return success message instead of token (since we need verify step)
        return {
            "message": "OTP sent to email",
            "email": user_data.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login")
async def login(credentials: UserLogin):
    """Login user and return OTP message or token for fast pass"""
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (credentials.email,))
        user = cursor.fetchone()
        

        if not user:
            cursor.close()
            connection.close()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
            
        # Generate OTP for all users
        otp_code = f"{random.randint(100000, 999999)}"
        otp_expiry = datetime.now() + timedelta(minutes=10)
        
        cursor.execute(
            "UPDATE users SET verification_code = %s, verification_code_expires = %s WHERE id = %s",
            (otp_code, otp_expiry, user["id"])
        )
        connection.commit()
        cursor.close()
        connection.close()
        
        send_otp_email(credentials.email, otp_code)
        
        return {
            "message": "OTP sent to email",
            "email": credentials.email
        }

        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@router.post("/verify", response_model=TokenResponse)
async def verify_otp(verify_data: UserVerify):
    """Verify OTP and return access token"""
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
        
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM pending_registrations WHERE email = %s AND verification_code = %s AND verification_code_expires > NOW()",
            (verify_data.email, verify_data.otp)
        )
        pending_user = cursor.fetchone()
        
        if pending_user:
            # Move to users table
            dummy_hash = "otp_auth_only"
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                """,
                (pending_user["username"], pending_user["email"], dummy_hash, pending_user["role"])
            )
            user_id = cursor.lastrowid
            
            cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending_user["id"],))
            connection.commit()
            
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
        else:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s AND verification_code = %s AND verification_code_expires > NOW()",
                (verify_data.email, verify_data.otp)
            )
            user = cursor.fetchone()
            
            if not user:
                # Check if it's because of wrong OTP or expired
                cursor.execute("SELECT id FROM users WHERE email = %s UNION SELECT id FROM pending_registrations WHERE email = %s", (verify_data.email, verify_data.email))
                if cursor.fetchone():
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")
                else:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
                    
            # Clear OTP
            cursor.execute(
                "UPDATE users SET verification_code = NULL, verification_code_expires = NULL WHERE id = %s",
                (user["id"],)
            )
            connection.commit()
        
        access_token = create_access_token(
            data={"user_id": user["id"], "username": user["username"], "role": user["role"]}
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )
    finally:
        cursor.close()
        connection.close()


@router.post("/resend-otp")
async def resend_otp(request: EmailRequest):
    """Resend OTP to existing user or pending registration"""
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection failed")
        
    try:
        cursor = connection.cursor(dictionary=True)
        # Check users table first (for login flow)
        cursor.execute("SELECT id FROM users WHERE email = %s", (request.email,))
        user = cursor.fetchone()
        
        otp_code = f"{random.randint(100000, 999999)}"
        otp_expiry = datetime.now() + timedelta(minutes=10)
        
        if user:
            cursor.execute(
                "UPDATE users SET verification_code = %s, verification_code_expires = %s WHERE id = %s",
                (otp_code, otp_expiry, user["id"])
            )
        else:
            # Check pending_registrations
            cursor.execute("SELECT id FROM pending_registrations WHERE email = %s", (request.email,))
            pending_user = cursor.fetchone()
            if pending_user:
                cursor.execute(
                    "UPDATE pending_registrations SET verification_code = %s, verification_code_expires = %s WHERE id = %s",
                    (otp_code, otp_expiry, pending_user["id"])
                )
            else:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
                
        connection.commit()
        send_otp_email(request.email, otp_code)
        
        return {"message": "OTP resent successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to resend OTP: {str(e)}")
    finally:
        cursor.close()
        connection.close()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user["role"],
        "created_at": str(current_user["created_at"])
    }


@router.get("/permissions")
async def get_my_permissions(current_user: dict = Depends(get_current_user)):
    """Get current user's permissions"""
    permissions = get_role_permissions(current_user["role"])
    return {
        "role": current_user["role"],
        "permissions": permissions
    }


@router.get("/users")
async def list_users(
    current_user: dict = Depends(require_permission(Permission.MANAGE_USERS))
):
    """List all users (Admin only)"""
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, role, created_at FROM users")
        users = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return {"users": users}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching users: {str(e)}"
        )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    new_role: str,
    current_user: dict = Depends(require_permission(Permission.MANAGE_USERS))
):
    """Update user role (Admin only)"""
    if new_role not in [Role.ADMIN, Role.USER, Role.VIEWER]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role"
        )
    
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET role = %s WHERE id = %s",
            (new_role, user_id)
        )
        connection.commit()
        cursor.close()
        connection.close()
        
        return {"message": f"User role updated to {new_role}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating role: {str(e)}"
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_permission(Permission.MANAGE_USERS))
):
    """Delete user (Admin only)"""
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    connection = get_db_connection()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        connection.commit()
        cursor.close()
        connection.close()
        
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user: {str(e)}"
        )

