from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db_connection
import uuid
import json
from datetime import datetime, timedelta
import jwt
from app.core.config import settings
from app.core.email import send_project_invite_email

router = APIRouter()

class AddMemberRequest(BaseModel):
    email: str
    role: str

@router.get("/{dataset_id}/members")
async def get_members(dataset_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        # Check if user has access to dataset (owner or existing member)
        cursor.execute("SELECT user_id FROM datasets WHERE id = %s", (dataset_id,))
        ds = cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        is_owner = ds['user_id'] == current_user['id']
        
        cursor.execute("SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        mem = cursor.fetchone()
        
        if not is_owner and not mem:
            raise HTTPException(status_code=403, detail="Not authorized")
            
        # Get all members
        query = """
            SELECT pm.id, pm.user_id, pm.role, u.email, u.username
            FROM project_members pm
            JOIN users u ON pm.user_id = u.id
            WHERE pm.dataset_id = %s
        """
        cursor.execute(query, (dataset_id,))
        members = cursor.fetchall()
        
        # Add owner explicitly 
        cursor.execute("SELECT id, email, username FROM users WHERE id = %s", (ds['user_id'],))
        owner = cursor.fetchone()
        if owner:
            # Check if owner is already in members list to avoid duplicates
            if not any(m['user_id'] == owner['id'] for m in members):
                members.insert(0, {
                    "id": f"owner_{owner['id']}",
                    "user_id": owner['id'],
                    "role": "owner",
                    "email": owner['email'],
                    "username": owner['username']
                })
        
        return {"members": members}
    finally:
        conn.close()

@router.post("/{dataset_id}/members")
async def add_member(dataset_id: str, req: AddMemberRequest, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        # Verify permissions (must be owner or admin)
        cursor.execute("SELECT user_id, name FROM datasets WHERE id = %s", (dataset_id,))
        ds = cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        is_owner = ds['user_id'] == current_user['id']
        cursor.execute("SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        mem = cursor.fetchone()
        
        if not is_owner and (not mem or mem['role'] != 'admin'):
            raise HTTPException(status_code=403, detail="Only owners and admins can add members")
            
        # Optional: verify if user exists beforehand to prevent duplicate invites, but we don't strictly reject if they don't exist
        cursor.execute("SELECT id FROM users WHERE email = %s", (req.email,))
        target_user = cursor.fetchone()
        
        if target_user:
            if target_user['id'] == ds['user_id']:
                raise HTTPException(status_code=400, detail="Cannot invite the project owner")
                
            cursor.execute("SELECT id FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, target_user['id']))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="User is already a member")
        
        # Generate JWT invite token
        invite_data = {
            "dataset_id": dataset_id,
            "dataset_name": ds['name'],
            "email": req.email,
            "role": req.role,
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        token = jwt.encode(invite_data, settings.secret_key, algorithm=settings.algorithm)
        invite_link = f"{settings.frontend_url}/project/invite?token={token}"
        
        inviter_name = current_user.get("username") or current_user.get("email")
        
        success = send_project_invite_email(
            to_email=req.email,
            inviter_name=inviter_name,
            project_name=ds['name'],
            role=req.role,
            invite_link=invite_link
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to dispatch invitation email")
            
        # Log activity
        cursor.execute(
            "INSERT INTO activity_logs (dataset_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
            (dataset_id, current_user['id'], "invite_sent", json.dumps({"target_email": req.email, "role": req.role}))
        )
        
        conn.commit()
        return {"success": True, "message": "Invitation sent successfully"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

class AcceptInviteRequest(BaseModel):
    token: str

@router.post("/invites/accept")
async def accept_invite(req: AcceptInviteRequest, current_user: dict = Depends(get_current_user)):
    try:
        payload = jwt.decode(req.token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("email")
        dataset_id = payload.get("dataset_id")
        role = payload.get("role")
        
        if not email or email.lower() != current_user.get("email", "").lower():
            raise HTTPException(status_code=403, detail="This invite was sent to a different email address. Please login with the correct account.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Invite link has expired.")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid invite link.")
        
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check if already a member
        cursor.execute("SELECT id FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        if cursor.fetchone():
            return {"success": True, "message": "Already a member", "dataset_id": dataset_id}
            
        # Verify dataset still exists
        cursor.execute("SELECT id FROM datasets WHERE id = %s", (dataset_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Dataset no longer exists")
            
        cursor.execute(
            "INSERT INTO project_members (dataset_id, user_id, role) VALUES (%s, %s, %s)",
            (dataset_id, current_user['id'], role)
        )
        
        # Log activity
        cursor.execute(
            "INSERT INTO activity_logs (dataset_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
            (dataset_id, current_user['id'], "member_joined", json.dumps({"role": role}))
        )
        
        conn.commit()
        return {"success": True, "message": "Successfully joined the project", "dataset_id": dataset_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/{dataset_id}/members/{user_id}")
async def remove_member(dataset_id: str, user_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        cursor = conn.cursor(dictionary=True)
        # Verify permissions
        cursor.execute("SELECT user_id FROM datasets WHERE id = %s", (dataset_id,))
        ds = cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        is_owner = ds['user_id'] == current_user['id']
        cursor.execute("SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        mem = cursor.fetchone()
        
        # can remove oneself, otherwise need admin/owner
        if current_user['id'] != user_id and not is_owner and (not mem or mem['role'] != 'admin'):
            raise HTTPException(status_code=403, detail="Not authorized to remove this member")
            
        cursor.execute("DELETE FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, user_id))
        
        # Log activity
        cursor.execute(
            "INSERT INTO activity_logs (dataset_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
            (dataset_id, current_user['id'], "member_removed", json.dumps({"target_user_id": user_id}))
        )
        
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/{dataset_id}/activity")
async def get_activity(dataset_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        cursor = conn.cursor(dictionary=True)
        # permission check
        cursor.execute("SELECT user_id FROM datasets WHERE id = %s", (dataset_id,))
        ds = cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        is_owner = ds['user_id'] == current_user['id']
        cursor.execute("SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        mem = cursor.fetchone()
        
        if not is_owner and not mem:
            raise HTTPException(status_code=403, detail="Not authorized")
            
        query = """
            SELECT a.id, a.action, a.details, a.created_at, u.username, u.email
            FROM activity_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.dataset_id = %s
            ORDER BY a.created_at DESC
            LIMIT 50
        """
        cursor.execute(query, (dataset_id,))
        logs = cursor.fetchall()
        
        # Parse details JSON
        import json
        for log in logs:
            if log['details'] and isinstance(log['details'], str):
                try:
                    log['details'] = json.loads(log['details'])
                except:
                    pass
            # Convert datetime to ISO string
            if hasattr(log['created_at'], 'isoformat'):
                log['created_at'] = log['created_at'].isoformat()
                
        return {"activity": logs}
    finally:
        conn.close()
