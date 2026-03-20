from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db_connection
import uuid
import datetime

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
        cursor.execute("SELECT user_id FROM datasets WHERE id = %s", (dataset_id,))
        ds = cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        is_owner = ds['user_id'] == current_user['id']
        cursor.execute("SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, current_user['id']))
        mem = cursor.fetchone()
        
        if not is_owner and (not mem or mem['role'] != 'admin'):
            raise HTTPException(status_code=403, detail="Only owners and admins can add members")
            
        # Find user by email
        cursor.execute("SELECT id FROM users WHERE email = %s", (req.email,))
        target_user = cursor.fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail="User with this email not found. They must sign up first.")
            
        if target_user['id'] == ds['user_id']:
            raise HTTPException(status_code=400, detail="Cannot add the project owner as a member")
            
        # Check if already member
        cursor.execute("SELECT id FROM project_members WHERE dataset_id = %s AND user_id = %s", (dataset_id, target_user['id']))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="User is already a member")
            
        # Insert
        cursor.execute(
            "INSERT INTO project_members (dataset_id, user_id, role) VALUES (%s, %s, %s)",
            (dataset_id, target_user['id'], req.role)
        )
        
        # Log activity
        cursor.execute(
            "INSERT INTO activity_logs (dataset_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
            (dataset_id, current_user['id'], "member_added", f'{{"target_email": "{req.email}", "role": "{req.role}"}}')
        )
        
        conn.commit()
        return {"success": True, "message": "Member added successfully"}
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
            (dataset_id, current_user['id'], "member_removed", f'{{"target_user_id": {user_id}}}')
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
