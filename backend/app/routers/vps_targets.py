from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ssh_sync
from ..database import get_db
from ..models import AdminUser, Secret, SecretVpsTarget, Server
from ..auth import get_current_user, log_action, get_client_ip
from ..crypto import decrypt_value
from ..rotation import push_to_single_target
from ..schemas import VpsTargetOut, VpsTargetCreate, VpsTargetUpdate, MessageResponse

router = APIRouter(prefix="/api/vps-targets", tags=["vps-targets"])


@router.get("", response_model=list[VpsTargetOut])
async def list_targets(
    secret_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    query = db.query(SecretVpsTarget)
    if secret_id is not None:
        query = query.filter(SecretVpsTarget.secret_id == secret_id)
    return query.order_by(SecretVpsTarget.created_at.desc()).all()


@router.post("", response_model=VpsTargetOut, status_code=201)
async def create_target(
    body: VpsTargetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == body.secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    server = db.query(Server).filter(Server.id == body.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    target = SecretVpsTarget(
        secret_id=body.secret_id,
        server_id=body.server_id,
        remote_path=body.remote_path.strip() or None,
        remote_key=body.remote_key.strip() or None,
        dry_run=body.dry_run,
    )
    db.add(target)
    db.flush()
    log_action(db, current_user, "create_vps_target", get_client_ip(request), "secret", secret.id, secret.name, {"server": server.name})
    db.commit()
    db.refresh(target)
    return target


@router.patch("/{target_id}", response_model=VpsTargetOut)
async def update_target(
    target_id: int,
    body: VpsTargetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    target.remote_path = body.remote_path.strip() or None
    target.remote_key = body.remote_key.strip() or None
    target.dry_run = body.dry_run
    log_action(db, current_user, "update_vps_target", get_client_ip(request), "secret", target.secret_id)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/{target_id}", response_model=MessageResponse)
async def delete_target(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    log_action(db, current_user, "delete_vps_target", get_client_ip(request), "secret", target.secret_id)
    db.delete(target)
    db.commit()
    return {"message": "Target removed"}


@router.post("/{target_id}/push", response_model=MessageResponse)
async def push_target(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    secret = target.secret
    try:
        plaintext = decrypt_value(secret.encrypted_value)
        result = push_to_single_target(target, secret.name, plaintext)
        log_action(db, current_user, "push_vps_target", get_client_ip(request), "secret", secret.id, secret.name)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Push failed: {str(e)[:120]}")
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=f"Push failed: {str(result.get('detail'))[:120]}")
    return {"message": "Pushed to server"}


@router.post("/{target_id}/test", response_model=MessageResponse)
async def test_target(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target or not target.server:
        raise HTTPException(status_code=404, detail="Target not found")
    server = target.server
    try:
        if not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Server is missing SSH connection details")
        if not server.ssh_key_secret:
            raise ssh_sync.SSHSyncError("Linked SSH key secret was not found")
        private_key_pem = decrypt_value(server.ssh_key_secret.encrypted_value)
        ssh_sync.test_connection(server.ssh_host, server.ssh_port or 22, server.ssh_username, private_key_pem)
        log_action(db, current_user, "test_vps_target", get_client_ip(request), "server", server.id, server.name)
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)[:120]}")
    return {"message": "Connection OK"}
