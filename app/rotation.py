import secrets as pysecrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import ssh_sync
from .crypto import encrypt_private_key, decrypt_private_key
from .models import AdminUser, AuditLog, Notification, Project, Secret, SecretVersion


def generate_random_value(length: int = 32) -> str:
    return pysecrets.token_urlsafe(length)


def compute_next_rotation(interval_days: int, now: datetime) -> datetime:
    return now + timedelta(days=interval_days)


def due_for_rotation(secret: Secret, now: datetime) -> bool:
    return (
        secret.rotation_mode in ("auto", "reminder")
        and bool(secret.rotation_interval_days)
        and secret.next_rotation_at is not None
        and secret.next_rotation_at <= now
    )


def rotate_secret_core(db: Session, secret: Secret, new_value: str, actor_name: str) -> Secret:
    """Snapshot the current value, overwrite it, and recompute the rotation schedule.
    Does not commit — caller commits (matches the existing route convention)."""
    db.add(SecretVersion(
        secret_id=secret.id,
        encrypted_value=secret.encrypted_value,
        rotated_by=actor_name,
    ))
    secret.encrypted_value = encrypt_private_key(new_value.strip())
    secret.rotated_at = datetime.utcnow()
    if secret.rotation_interval_days:
        secret.next_rotation_at = compute_next_rotation(secret.rotation_interval_days, datetime.utcnow())
    return secret


def push_to_single_target(target, secret_name: str, plaintext_value: str) -> dict:
    """Push plaintext_value to one VPS target. Mutates the target's status fields.
    Does not commit — caller commits."""
    server = target.server
    result = {"target_id": target.id, "server": server.name if server else None}
    try:
        if not server or not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Server is missing SSH connection details")
        key_secret = server.ssh_key_secret
        if not key_secret:
            raise ssh_sync.SSHSyncError("Server's SSH key secret was not found")
        private_key_pem = decrypt_private_key(key_secret.encrypted_value)
        remote_path = target.remote_path or server.default_env_path or ".env"
        remote_key = target.remote_key or secret_name
        push_result = ssh_sync.upsert_env_line(
            host=server.ssh_host,
            port=server.ssh_port or 22,
            username=server.ssh_username,
            private_key_pem=private_key_pem,
            remote_path=remote_path,
            key=remote_key,
            value=plaintext_value,
            dry_run=target.dry_run,
        )
        target.last_synced_at = datetime.utcnow()
        target.last_sync_status = "dry_run" if push_result.get("dry_run") else "success"
        target.last_sync_error = None
        result.update({"status": target.last_sync_status, "detail": push_result.get("action")})
    except Exception as exc:
        target.last_synced_at = datetime.utcnow()
        target.last_sync_status = "failed"
        target.last_sync_error = str(exc)[:2000]
        result.update({"status": "failed", "detail": str(exc)})
    return result


def push_secret_to_targets(db: Session, secret: Secret, plaintext_value: str) -> list[dict]:
    """Push plaintext_value to every VPS target of secret. One target failing does not
    abort the others. Does not commit — caller commits."""
    return [push_to_single_target(target, secret.name, plaintext_value) for target in secret.vps_targets]


def run_scheduled_rotation_check(db: Session) -> dict:
    """Called only by the backend/app/ scheduler. For 'auto' secrets: generate a new
    value, rotate, and push. For 'reminder' secrets: notify admins without changing
    the value. Commits at the end."""
    now = datetime.utcnow()
    auto_rotated = []
    reminders_sent = []
    errors = []

    due_secrets = (
        db.query(Secret)
        .filter(Secret.rotation_mode.in_(("auto", "reminder")))
        .filter(Secret.rotation_interval_days.isnot(None))
        .filter(Secret.next_rotation_at.isnot(None))
        .filter(Secret.next_rotation_at <= now)
        .all()
    )

    for secret in due_secrets:
        try:
            if secret.rotation_mode == "auto":
                new_value = generate_random_value()
                rotate_secret_core(db, secret, new_value, actor_name="scheduler")
                push_secret_to_targets(db, secret, new_value)
                secret.last_rotation_status = "success"
                secret.last_rotation_error = None
                db.add(AuditLog(
                    actor_name="scheduler",
                    action="auto_rotate_secret",
                    resource_type="secret",
                    resource_id=str(secret.id),
                    resource_name=secret.name,
                ))
                auto_rotated.append(secret.id)
            elif secret.rotation_mode == "reminder":
                admins = (
                    db.query(AdminUser)
                    .filter(AdminUser.role.in_(("SUPER_OWNER", "ADMIN")))
                    .filter(AdminUser.status == "active")
                    .all()
                )
                for admin in admins:
                    db.add(Notification(
                        recipient_id=admin.id,
                        title=f"Rotation due: {secret.name}",
                        message=f"Secret '{secret.name}' is due for rotation. Rotate it manually from the Secrets Vault.",
                        type="warning",
                    ))
                secret.next_rotation_at = compute_next_rotation(secret.rotation_interval_days, now)
                secret.last_rotation_status = "reminder_sent"
                db.add(AuditLog(
                    actor_name="scheduler",
                    action="rotation_reminder_sent",
                    resource_type="secret",
                    resource_id=str(secret.id),
                    resource_name=secret.name,
                ))
                reminders_sent.append(secret.id)
        except Exception as exc:
            secret.last_rotation_status = "failed"
            secret.last_rotation_error = str(exc)[:2000]
            errors.append({"secret_id": secret.id, "error": str(exc)})

    db.commit()
    return {"auto_rotated": auto_rotated, "reminders_sent": reminders_sent, "errors": errors}


def restart_project(db: Session, project: Project) -> dict:
    """Run the project's configured restart command over SSH. Manual trigger only —
    never called from the rotation scheduler. Does not commit — caller commits."""
    server = project.restart_server
    result = {"status": None, "output": ""}
    try:
        if not server or not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Restart server is missing SSH connection details")
        if not project.restart_command:
            raise ssh_sync.SSHSyncError("No restart command configured for this project")
        key_secret = server.ssh_key_secret
        if not key_secret:
            raise ssh_sync.SSHSyncError("Server's SSH key secret was not found")
        private_key_pem = decrypt_private_key(key_secret.encrypted_value)
        run_result = ssh_sync.run_command(
            host=server.ssh_host,
            port=server.ssh_port or 22,
            username=server.ssh_username,
            private_key_pem=private_key_pem,
            command=project.restart_command,
            dry_run=project.restart_dry_run,
        )
        if run_result.get("dry_run"):
            result["status"] = "dry_run"
            result["output"] = run_result["action"]
        elif run_result.get("exit_code") == 0:
            result["status"] = "success"
            result["output"] = run_result.get("stdout") or "(no output)"
        else:
            result["status"] = "failed"
            output = (run_result.get("stderr") or run_result.get("stdout") or "").strip()
            result["output"] = output[:2000] or f"Command exited with code {run_result.get('exit_code')}"
    except Exception as exc:
        result["status"] = "failed"
        result["output"] = str(exc)[:2000]

    project.last_restart_at = datetime.utcnow()
    project.last_restart_status = result["status"]
    project.last_restart_output = result["output"]
    return result
