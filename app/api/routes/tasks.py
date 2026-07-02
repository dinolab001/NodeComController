from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select
from app.services.db import get_session
from app.models import Task, StorageDrive, DriveAssignment, Group, TaskSnapshot
from typing import Optional, Dict, Any
import uuid
import json

router = APIRouter()


class UploadQuotaRequest(BaseModel):
    group_id: str
    group_token: str
    estimated_size_bytes: int


class UploadVerifyRequest(BaseModel):
    group_id: str
    group_token: str
    drive_file_id: str
    checksum: str
    task_id: str


class SnapshotRequest(BaseModel):
    group_id: str
    group_token: str
    node_id: str
    tcb_snapshot: Dict[str, Any]
    global_state: Optional[str] = None


class LeaderFailoverRequest(BaseModel):
    group_id: str
    group_token: str
    new_leader_id: str


def _verify_group_token(group_id: str, group_token: str, session: Session) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.group_token != group_token:
        raise HTTPException(status_code=403, detail="Invalid group token")
    return group


@router.post("/tasks/quota")
def request_upload_quota(request: UploadQuotaRequest, session: Session = Depends(get_session)):
    """
    Leader node requests upload quota. Controller picks the drive with most remaining space.
    """
    group = _verify_group_token(request.group_id, request.group_token, session)

    # Get all drives sorted by remaining space descending
    drives = session.exec(select(StorageDrive)).all()
    if not drives:
        raise HTTPException(status_code=503, detail="No storage drives available")

    best_drive = max(drives, key=lambda d: d.remaining_space or 0)

    if (best_drive.remaining_space or 0) < request.estimated_size_bytes:
        raise HTTPException(status_code=507, detail="Insufficient storage space on all drives")

    # Upsert a drive assignment for the group's task
    assignment = session.exec(
        select(DriveAssignment).where(DriveAssignment.task_id == group.task_id)
    ).first()

    if not assignment:
        assignment = DriveAssignment(
            task_id=group.task_id,
            drive_id=best_drive.id,
            folder_path=f"tasks/{group.task_id}"
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)

    # Load drive credentials and return them (DO NOT return refresh token)
    creds = best_drive.credentials or {}
    safe_creds = {k: v for k, v in creds.items() if k != "refresh_token"}

    return {
        "status": "approved",
        "drive_id": best_drive.drive_id,
        "folder_path": assignment.folder_path,
        "credentials": safe_creds,
    }


@router.post("/tasks/upload/verify")
def verify_upload(request: UploadVerifyRequest, session: Session = Depends(get_session)):
    """
    Leader submits the Drive file ID + checksum after upload.
    Controller verifies the file exists, then credits accounts.
    """
    group = _verify_group_token(request.group_id, request.group_token, session)

    # Get the drive assignment to know which drive to check
    assignment = session.exec(
        select(DriveAssignment).where(DriveAssignment.task_id == request.task_id)
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="No drive assignment found for this task")

    drive = session.get(StorageDrive, assignment.drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")

    # TODO: Integrate Google Drive API verification here
    # For now, we trust the submission and update the task state
    task = session.get(Task, request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    tcb = task.global_TCB or {}
    tcb["upload_verified"] = True
    tcb["drive_file_id"] = request.drive_file_id
    tcb["checksum"] = request.checksum
    task.global_TCB = tcb
    task.global_State = "COMPLETED"
    session.add(task)
    session.commit()

    return {"status": "verified", "task_id": request.task_id}


@router.post("/tasks/snapshot")
def receive_snapshot(request: SnapshotRequest, session: Session = Depends(get_session)):
    """
    Receive periodic TCB snapshot from the leader node and persist it.
    """
    group = _verify_group_token(request.group_id, request.group_token, session)

    snapshot = TaskSnapshot(
        node_id=request.node_id,
        TCB_snapshot=request.tcb_snapshot,
    )
    session.add(snapshot)

    # Also update the task global state if provided
    if request.global_state and group.task_id:
        task = session.get(Task, group.task_id)
        if task:
            task.global_State = request.global_state
            task.global_TCB = request.tcb_snapshot
            session.add(task)

    session.commit()
    return {"status": "snapshot_saved"}


@router.post("/groups/failover")
def leader_failover(request: LeaderFailoverRequest, session: Session = Depends(get_session)):
    """
    A newly elected leader node notifies the controller after the previous leader failed.
    """
    group = _verify_group_token(request.group_id, request.group_token, session)

    from app.models import ComputeNode
    new_leader = session.get(ComputeNode, request.new_leader_id)
    if not new_leader:
        raise HTTPException(status_code=404, detail="New leader node not found")

    # Update old leader status if possible
    if group.group_lead:
        old_leader = session.get(ComputeNode, group.group_lead)
        if old_leader:
            old_leader.status = "DISCONNECTED"
            session.add(old_leader)

    # Update group leader
    group.group_lead = request.new_leader_id
    session.add(group)

    # Update new leader node status
    new_leader.status = "LEADER"
    session.add(new_leader)

    session.commit()
    return {"status": "failover_complete", "new_leader": request.new_leader_id}
