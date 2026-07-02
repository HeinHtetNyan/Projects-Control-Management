from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Secret, SecretVersion, Server, AdminUser
from ..auth import get_current_user, log_action, get_client_ip
from ..crypto import encrypt_value, decrypt_value
from ..config import settings
from ..rotation import (
    generate_random_value, rotate_secret_core, push_secret_to_targets,
    compute_next_rotation,
)
from ..schemas import (
    SecretOut, SecretCreate, SecretRotate, SecretRevealed,
    SecretVersionOut, SecretRotationSettings, MessageResponse,
)

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


@router.get("", response_model=list[SecretOut])
async def list_secrets(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    return db.query(Secret).order_by(Secret.created_at.desc()).all()


@router.post("", response_model=SecretOut, status_code=201)
async def create_secret(
    body: SecretCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    if not settings.ENCRYPTION_KEY:
        raise HTTPException(status_code=400, detail="ENCRYPTION_KEY not set on server")
    try:
        encrypted = encrypt_value(body.value.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Encryption failed: {str(e)[:80]}")

    mode = body.rotation_mode if body.rotation_mode in ("manual", "auto", "reminder") else "manual"
    next_rotation = (
        compute_next_rotation(body.rotation_interval_days, datetime.utcnow())
        if (mode != "manual" and body.rotation_interval_days) else None
    )
    secret = Secret(
        name=body.name.strip(),
        category=body.category.strip(),
        encrypted_value=encrypted,
        project_id=body.project_id,
        environment=body.environment.strip() or None,
        description=body.description.strip() or None,
        created_by=current_user.username,
        rotation_mode=mode,
        rotation_interval_days=body.rotation_interval_days,
        next_rotation_at=next_rotation,
    )
    db.add(secret)
    db.flush()
    log_action(db, current_user, "create_secret", get_client_ip(request), "secret", secret.id, secret.name, {"category": body.category})
    db.commit()
    db.refresh(secret)
    return secret


@router.patch("/{secret_id}/rotation-settings", response_model=SecretOut)
async def update_rotation_settings(
    secret_id: int,
    body: SecretRotationSettings,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    mode = body.rotation_mode if body.rotation_mode in ("manual", "auto", "reminder") else "manual"
    secret.rotation_mode = mode
    secret.rotation_interval_days = body.rotation_interval_days
    secret.next_rotation_at = (
        compute_next_rotation(body.rotation_interval_days, datetime.utcnow())
        if (mode != "manual" and body.rotation_interval_days) else None
    )
    log_action(db, current_user, "update_secret_rotation_settings", get_client_ip(request), "secret", secret_id, secret.name,
               {"rotation_mode": mode, "rotation_interval_days": body.rotation_interval_days})
    db.commit()
    db.refresh(secret)
    return secret


@router.post("/{secret_id}/reveal", response_model=SecretRevealed)
async def reveal_secret(
    secret_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    try:
        plaintext = decrypt_value(secret.encrypted_value)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decrypt failed: {str(e)[:80]}")
    log_action(db, current_user, "reveal_secret", get_client_ip(request), "secret", secret_id, secret.name)
    db.commit()
    return SecretRevealed(id=secret.id, name=secret.name, value=plaintext)


@router.post("/{secret_id}/rotate", response_model=SecretOut)
async def rotate_secret(
    secret_id: int,
    body: SecretRotate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    value = (body.new_value or "").strip()
    if not value:
        if secret.rotation_mode != "auto":
            raise HTTPException(status_code=400, detail="new_value is required for manual/reminder secrets")
        value = generate_random_value()
    try:
        rotate_secret_core(db, secret, value, actor_name=current_user.username)
        push_results = push_secret_to_targets(db, secret, value)
        secret.last_rotation_status = "success"
        secret.last_rotation_error = None
        log_action(db, current_user, "rotate_secret", get_client_ip(request), "secret", secret_id, secret.name,
                   {"targets_pushed": len(push_results)})
        db.commit()
        db.refresh(secret)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Rotation failed: {str(e)[:80]}")
    return secret


@router.delete("/{secret_id}", response_model=MessageResponse)
async def delete_secret(
    secret_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    blocking = db.query(Server).filter(Server.ssh_key_secret_id == secret_id).first()
    if blocking:
        raise HTTPException(status_code=400, detail=f"Secret is used as the SSH key for server '{blocking.name}' — unlink it first")
    log_action(db, current_user, "delete_secret", get_client_ip(request), "secret", secret_id, secret.name)
    db.delete(secret)
    db.commit()
    return {"message": "Secret deleted"}


@router.get("/{secret_id}/versions", response_model=list[SecretVersionOut])
async def list_versions(
    secret_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    return (
        db.query(SecretVersion)
        .filter(SecretVersion.secret_id == secret_id)
        .order_by(SecretVersion.created_at.desc())
        .all()
    )


@router.post("/{secret_id}/versions/{version_id}/restore", response_model=SecretOut)
async def restore_version(
    secret_id: int,
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    from datetime import datetime
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    version = db.query(SecretVersion).filter(
        SecretVersion.id == version_id, SecretVersion.secret_id == secret_id
    ).first()
    if not secret or not version:
        raise HTTPException(status_code=404, detail="Secret or version not found")
    db.add(SecretVersion(
        secret_id=secret_id,
        encrypted_value=secret.encrypted_value,
        rotated_by=f"{current_user.username} (before restore)",
    ))
    secret.encrypted_value = version.encrypted_value
    secret.rotated_at = datetime.utcnow()
    log_action(db, current_user, "restore_secret_version", get_client_ip(request), "secret", secret_id, secret.name, {"version_id": version_id})
    db.commit()
    db.refresh(secret)
    return secret
