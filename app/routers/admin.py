"""
Admin web dashboard — all pages and form-POST actions.
All routes require an authenticated session.
"""
import json
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import (
    AdminUser, Project, Customer, ActivationToken, License,
    Device, Server, Deployment, Secret, SecretVersion, SecretVpsTarget,
    Domain, Integration, Note, AuditLog, Notification,
)
from ..crypto import (
    generate_key_pair, derive_public_key,
    encrypt_private_key, decrypt_private_key,
)
from ..auth import hash_password, verify_password, require_login, login_redirect
from ..templates_config import templates
from ..config import settings
from .. import ssh_sync
from ..rotation import (
    generate_random_value, rotate_secret_core, push_secret_to_targets,
    push_to_single_target, compute_next_rotation, restart_project,
)

router = APIRouter(prefix="/admin")


# Auth helpers

def _ctx(request: Request, db: Session, **extra):
    user = require_login(request, db)
    unread_count = 0
    if user:
        unread_count = db.query(Notification).filter(
            Notification.recipient_id == user.id,
            Notification.is_read == False,
        ).count()
    return {"user": user, "app_name": settings.APP_NAME, "unread_count": unread_count, **extra}


def _guard(request: Request, db: Session):
    user = require_login(request, db)
    if not user:
        return None, login_redirect()
    return user, None


def _log(db: Session, request: Request, user: AdminUser, action: str,
         resource_type: str = None, resource_id: str = None,
         resource_name: str = None, meta: dict = None):
    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(
        actor_id=user.id,
        actor_name=user.username,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        resource_name=resource_name,
        extra_data=json.dumps(meta) if meta else None,
        ip_address=ip,
    ))


# Login / Logout

@router.get("/login")
async def login_page(request: Request, error: str = "", db: Session = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse(
        request, "login.html",
        {"error": error, "app_name": settings.APP_NAME},
    )


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse("/admin/login?error=Invalid+username+or+password", status_code=302)
    if user.status == "suspended":
        return RedirectResponse("/admin/login?error=Your+account+has+been+suspended", status_code=302)
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    _log(db, request, user, "login")
    db.commit()
    return RedirectResponse("/admin/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if user:
            _log(db, request, user, "logout")
            db.commit()
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


# Dashboard

@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user, redir = _guard(request, db)
    if redir:
        return redir

    total_projects = db.query(Project).count()
    total_customers = db.query(Customer).count()
    pending_tokens = db.query(ActivationToken).filter(ActivationToken.status == "pending").count()
    active_licenses = db.query(License).filter(License.is_active == True).count()
    total_devices = db.query(Device).count()
    online_servers = db.query(Server).filter(Server.status == "running").count()
    total_servers = db.query(Server).count()

    recent_tokens = (
        db.query(ActivationToken)
        .order_by(ActivationToken.created_at.desc())
        .limit(6).all()
    )
    recent_licenses = (
        db.query(License)
        .order_by(License.activated_at.desc())
        .limit(6).all()
    )
    recent_audit = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(8).all()
    )

    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            **_ctx(request, db),
            "active_page": "dashboard",
            "total_projects": total_projects,
            "total_customers": total_customers,
            "pending_tokens": pending_tokens,
            "active_licenses": active_licenses,
            "total_devices": total_devices,
            "online_servers": online_servers,
            "total_servers": total_servers,
            "recent_tokens": recent_tokens,
            "recent_licenses": recent_licenses,
            "recent_audit": recent_audit,
        },
    )


# Projects

@router.get("/projects")
async def projects_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "projects.html",
        {**_ctx(request, db), "active_page": "projects",
         "projects": projects, "success": success, "error": error},
    )


@router.post("/projects/create")
async def project_create(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    deep_link_scheme: str = Form(...),
    type: str = Form(""),
    status: str = Form("Development"),
    version: str = Form(""),
    import_private_key: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir

    slug = slug.strip().lower().replace(" ", "-")
    if db.query(Project).filter(Project.slug == slug).first():
        return RedirectResponse(f"/admin/projects?error=Slug+%22{slug}%22+already+exists", status_code=302)

    if not settings.ENCRYPTION_KEY:
        return RedirectResponse("/admin/projects?error=ENCRYPTION_KEY+not+set+in+.env", status_code=302)

    try:
        if import_private_key.strip():
            private_b64 = import_private_key.strip()
            public_b64 = derive_public_key(private_b64)
        else:
            public_b64, private_b64 = generate_key_pair()
        private_enc = encrypt_private_key(private_b64)
    except Exception as e:
        return RedirectResponse(f"/admin/projects?error=Key+error:+{str(e)[:60]}", status_code=302)

    project = Project(
        name=name.strip(),
        slug=slug,
        description=description.strip(),
        deep_link_scheme=deep_link_scheme.strip(),
        public_key_b64=public_b64,
        private_key_enc=private_enc,
        type=type.strip() or None,
        status=status.strip() or "Development",
        version=version.strip() or None,
    )
    db.add(project)
    db.flush()
    _log(db, request, user, "create_project", "project", project.id, project.name)
    db.commit()
    return RedirectResponse(f"/admin/projects/{project.id}?success=Project+created", status_code=302)


@router.get("/projects/{project_id}")
async def project_detail(
    project_id: int,
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/admin/projects?error=Project+not+found", status_code=302)
    tokens = (
        db.query(ActivationToken)
        .filter(ActivationToken.project_id == project_id)
        .order_by(ActivationToken.created_at.desc())
        .limit(20).all()
    )
    project_secrets = (
        db.query(Secret)
        .filter(Secret.project_id == project_id)
        .order_by(Secret.created_at.desc())
        .all()
    )
    servers = db.query(Server).order_by(Server.name).all()
    return templates.TemplateResponse(
        request, "project_detail.html",
        {**_ctx(request, db), "active_page": "projects",
         "project": project, "tokens": tokens, "project_secrets": project_secrets,
         "servers": servers, "success": success, "error": error},
    )


@router.post("/projects/{project_id}/restart-settings")
async def project_restart_settings(
    project_id: int,
    request: Request,
    restart_server_id: str = Form(""),
    restart_command: str = Form(""),
    go_live: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/admin/projects?error=Project+not+found", status_code=302)
    project.restart_server_id = int(restart_server_id) if restart_server_id.strip() else None
    project.restart_command = restart_command.strip() or None
    project.restart_dry_run = (go_live != "on")
    _log(db, request, user, "update_restart_settings", "project", project_id, project.name)
    db.commit()
    return RedirectResponse(f"/admin/projects/{project_id}?success=Restart+settings+saved", status_code=302)


@router.post("/projects/{project_id}/restart")
async def project_restart(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/admin/projects?error=Project+not+found", status_code=302)
    result = restart_project(db, project)
    _log(db, request, user, "restart_project", "project", project_id, project.name, {"status": result["status"]})
    db.commit()
    if result["status"] == "failed":
        return RedirectResponse(
            f"/admin/projects/{project_id}?error=Restart+failed:+{result['output'][:100]}", status_code=302
        )
    label = "Dry-run" if result["status"] == "dry_run" else "Restart"
    return RedirectResponse(f"/admin/projects/{project_id}?success={label}+completed", status_code=302)


@router.post("/projects/{project_id}/update")
async def project_update(
    project_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    type: str = Form(""),
    status: str = Form(""),
    version: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/admin/projects?error=Project+not+found", status_code=302)
    project.name = name.strip()
    project.description = description.strip()
    project.type = type.strip() or None
    project.status = status.strip() or project.status
    project.version = version.strip() or None
    _log(db, request, user, "update_project", "project", project_id, project.name)
    db.commit()
    return RedirectResponse(f"/admin/projects/{project_id}?success=Project+updated", status_code=302)


@router.post("/projects/{project_id}/reimport-key")
async def project_reimport_key(
    project_id: int,
    request: Request,
    private_key: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/admin/projects?error=Project+not+found", status_code=302)
    try:
        public_b64 = derive_public_key(private_key.strip())
        project.public_key_b64 = public_b64
        project.private_key_enc = encrypt_private_key(private_key.strip())
        _log(db, request, user, "reimport_key", "project", project_id, project.name)
        db.commit()
    except Exception as e:
        return RedirectResponse(
            f"/admin/projects/{project_id}?error=Key+import+failed:+{str(e)[:60]}", status_code=302
        )
    return RedirectResponse(f"/admin/projects/{project_id}?success=Key+pair+updated", status_code=302)


@router.post("/projects/{project_id}/delete")
async def project_delete(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        _log(db, request, user, "delete_project", "project", project_id, project.name)
        db.delete(project)
        db.commit()
    return RedirectResponse("/admin/projects?success=Project+deleted", status_code=302)


# Customers

@router.get("/customers")
async def customers_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "customers.html",
        {**_ctx(request, db), "active_page": "customers",
         "customers": customers, "success": success, "error": error},
    )


@router.post("/customers/create")
async def customer_create(
    request: Request,
    name: str = Form(...),
    company_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    customer = Customer(
        name=name.strip(),
        company_name=company_name.strip() or None,
        email=email.strip() or None,
        phone=phone.strip() or None,
        country=country.strip() or None,
        notes=notes.strip() or None,
        status="active",
    )
    db.add(customer)
    db.flush()
    _log(db, request, user, "create_customer", "customer", customer.id, customer.name)
    db.commit()
    return RedirectResponse("/admin/customers?success=Customer+added", status_code=302)


@router.post("/customers/{customer_id}/update")
async def customer_update(
    customer_id: int,
    request: Request,
    name: str = Form(...),
    company_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        return RedirectResponse("/admin/customers?error=Customer+not+found", status_code=302)
    customer.name = name.strip()
    customer.company_name = company_name.strip() or None
    customer.email = email.strip() or None
    customer.phone = phone.strip() or None
    customer.country = country.strip() or None
    customer.notes = notes.strip() or None
    customer.status = status.strip()
    _log(db, request, user, "update_customer", "customer", customer_id, customer.name)
    db.commit()
    return RedirectResponse(f"/admin/customers?success=Customer+updated", status_code=302)


@router.post("/customers/{customer_id}/delete")
async def customer_delete(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        _log(db, request, user, "delete_customer", "customer", customer_id, customer.name)
        db.delete(customer)
        db.commit()
    return RedirectResponse("/admin/customers?success=Customer+deleted", status_code=302)


# Tokens

@router.get("/tokens")
async def tokens_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    tokens = db.query(ActivationToken).order_by(ActivationToken.created_at.desc()).all()
    projects = db.query(Project).order_by(Project.name).all()
    customers = db.query(Customer).order_by(Customer.name).all()
    return templates.TemplateResponse(
        request, "tokens.html",
        {**_ctx(request, db), "active_page": "tokens",
         "tokens": tokens, "projects": projects, "customers": customers,
         "success": success, "error": error,
         "base_url": settings.BASE_URL},
    )


@router.post("/tokens/create")
async def token_create(
    request: Request,
    project_id: int = Form(...),
    customer_id: int = Form(...),
    license_number: str = Form(...),
    license_type: str = Form("lifetime"),
    expires_days: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir

    project = db.query(Project).filter(Project.id == project_id).first()
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not project or not customer:
        return RedirectResponse("/admin/tokens?error=Invalid+project+or+customer", status_code=302)

    expires_at = None
    if expires_days.strip():
        try:
            expires_at = datetime.utcnow() + timedelta(days=int(expires_days))
        except ValueError:
            pass

    token_value = secrets.token_urlsafe(32)
    token = ActivationToken(
        token=token_value,
        project_id=project_id,
        customer_id=customer_id,
        license_number=license_number.strip(),
        license_type=license_type.strip(),
        expires_at=expires_at,
    )
    db.add(token)
    db.flush()
    _log(db, request, user, "create_token", "token", token.id, license_number,
         {"project": project.name, "customer": customer.name})
    db.commit()
    return RedirectResponse(f"/admin/tokens/{token.id}", status_code=302)


@router.get("/tokens/{token_id}")
async def token_detail(
    token_id: int,
    request: Request,
    success: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    token = db.query(ActivationToken).filter(ActivationToken.id == token_id).first()
    if not token:
        return RedirectResponse("/admin/tokens?error=Token+not+found", status_code=302)
    activation_url = f"{settings.BASE_URL}/activate?token={token.token}"
    return templates.TemplateResponse(
        request, "token_detail.html",
        {**_ctx(request, db), "active_page": "tokens",
         "token": token, "activation_url": activation_url, "success": success},
    )


@router.post("/tokens/{token_id}/revoke")
async def token_revoke(
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    token = db.query(ActivationToken).filter(ActivationToken.id == token_id).first()
    if token and token.status == "pending":
        token.status = "revoked"
        _log(db, request, user, "revoke_token", "token", token_id, token.license_number)
        db.commit()
    return RedirectResponse(f"/admin/tokens/{token_id}?success=Token+revoked", status_code=302)


# Licenses

@router.get("/licenses")
async def licenses_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    licenses = db.query(License).order_by(License.activated_at.desc()).all()
    return templates.TemplateResponse(
        request, "licenses.html",
        {**_ctx(request, db), "active_page": "licenses",
         "licenses": licenses, "success": success, "error": error},
    )


@router.post("/licenses/{license_id}/deactivate")
async def license_deactivate(
    license_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    lic = db.query(License).filter(License.id == license_id).first()
    if lic and lic.is_active:
        lic.is_active = False
        lic.deactivated_at = datetime.utcnow()
        _log(db, request, user, "deactivate_license", "license", license_id, lic.license_number)
        db.commit()
    return RedirectResponse("/admin/licenses?success=License+deactivated", status_code=302)


# Devices

@router.get("/devices")
async def devices_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    devices = db.query(Device).order_by(Device.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "devices.html",
        {**_ctx(request, db), "active_page": "devices",
         "devices": devices, "success": success, "error": error},
    )


@router.post("/devices/{device_id}/block")
async def device_block(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    device = db.query(Device).filter(Device.id == device_id).first()
    if device:
        device.status = "blocked"
        device.blocked_at = datetime.utcnow()
        _log(db, request, user, "block_device", "device", device_id, device.hostname or device.fingerprint)
        db.commit()
    return RedirectResponse("/admin/devices?success=Device+blocked", status_code=302)


@router.post("/devices/{device_id}/unblock")
async def device_unblock(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    device = db.query(Device).filter(Device.id == device_id).first()
    if device:
        device.status = "online"
        device.blocked_at = None
        _log(db, request, user, "unblock_device", "device", device_id, device.hostname or device.fingerprint)
        db.commit()
    return RedirectResponse("/admin/devices?success=Device+unblocked", status_code=302)


# Servers

@router.get("/servers")
async def servers_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    servers = db.query(Server).order_by(Server.created_at.desc()).all()
    ssh_key_secrets = db.query(Secret).order_by(Secret.name).all()
    return templates.TemplateResponse(
        request, "servers.html",
        {**_ctx(request, db), "active_page": "servers",
         "servers": servers, "ssh_key_secrets": ssh_key_secrets,
         "success": success, "error": error},
    )


@router.post("/servers/create")
async def server_create(
    request: Request,
    name: str = Form(...),
    provider: str = Form(""),
    ip_address: str = Form(""),
    cpu: str = Form(""),
    ram: str = Form(""),
    storage: str = Form(""),
    operating_system: str = Form(""),
    status: str = Form("running"),
    notes: str = Form(""),
    ssh_host: str = Form(""),
    ssh_port: str = Form("22"),
    ssh_username: str = Form(""),
    ssh_key_secret_id: str = Form(""),
    default_env_path: str = Form(".env"),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    server = Server(
        name=name.strip(),
        provider=provider.strip() or None,
        ip_address=ip_address.strip() or None,
        cpu=cpu.strip() or None,
        ram=ram.strip() or None,
        storage=storage.strip() or None,
        operating_system=operating_system.strip() or None,
        status=status.strip(),
        notes=notes.strip() or None,
        ssh_host=ssh_host.strip() or None,
        ssh_port=int(ssh_port) if ssh_port.strip() else 22,
        ssh_username=ssh_username.strip() or None,
        ssh_key_secret_id=int(ssh_key_secret_id) if ssh_key_secret_id.strip() else None,
        default_env_path=default_env_path.strip() or ".env",
    )
    db.add(server)
    db.flush()
    _log(db, request, user, "create_server", "server", server.id, server.name)
    db.commit()
    return RedirectResponse("/admin/servers?success=Server+added", status_code=302)


@router.post("/servers/{server_id}/update")
async def server_update(
    server_id: int,
    request: Request,
    name: str = Form(...),
    provider: str = Form(""),
    ip_address: str = Form(""),
    cpu: str = Form(""),
    ram: str = Form(""),
    storage: str = Form(""),
    operating_system: str = Form(""),
    notes: str = Form(""),
    ssh_host: str = Form(""),
    ssh_port: str = Form("22"),
    ssh_username: str = Form(""),
    ssh_key_secret_id: str = Form(""),
    default_env_path: str = Form(".env"),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        return RedirectResponse("/admin/servers?error=Server+not+found", status_code=302)
    server.name = name.strip()
    server.provider = provider.strip() or None
    server.ip_address = ip_address.strip() or None
    server.cpu = cpu.strip() or None
    server.ram = ram.strip() or None
    server.storage = storage.strip() or None
    server.operating_system = operating_system.strip() or None
    server.notes = notes.strip() or None
    server.ssh_host = ssh_host.strip() or None
    server.ssh_port = int(ssh_port) if ssh_port.strip() else 22
    server.ssh_username = ssh_username.strip() or None
    server.ssh_key_secret_id = int(ssh_key_secret_id) if ssh_key_secret_id.strip() else None
    server.default_env_path = default_env_path.strip() or ".env"
    _log(db, request, user, "update_server", "server", server_id, server.name)
    db.commit()
    return RedirectResponse("/admin/servers?success=Server+updated", status_code=302)


@router.post("/servers/{server_id}/test-ssh")
async def server_test_ssh(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        return RedirectResponse("/admin/servers?error=Server+not+found", status_code=302)
    try:
        if not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Server is missing SSH connection details")
        if not server.ssh_key_secret:
            raise ssh_sync.SSHSyncError("Linked SSH key secret was not found")
        private_key_pem = decrypt_private_key(server.ssh_key_secret.encrypted_value)
        ssh_sync.test_connection(server.ssh_host, server.ssh_port or 22, server.ssh_username, private_key_pem)
        _log(db, request, user, "test_server_ssh", "server", server_id, server.name)
        db.commit()
    except Exception as e:
        return RedirectResponse(f"/admin/servers?error=Connection+failed:+{str(e)[:80]}", status_code=302)
    return RedirectResponse("/admin/servers?success=Connection+OK", status_code=302)


@router.post("/servers/{server_id}/update-status")
async def server_update_status(
    server_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    server = db.query(Server).filter(Server.id == server_id).first()
    if server:
        server.status = status
        _log(db, request, user, "update_server_status", "server", server_id, server.name, {"status": status})
        db.commit()
    return RedirectResponse("/admin/servers?success=Server+status+updated", status_code=302)


@router.post("/servers/{server_id}/delete")
async def server_delete(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    server = db.query(Server).filter(Server.id == server_id).first()
    if server:
        _log(db, request, user, "delete_server", "server", server_id, server.name)
        db.delete(server)
        db.commit()
    return RedirectResponse("/admin/servers?success=Server+deleted", status_code=302)


# Deployments

@router.get("/deployments")
async def deployments_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    deployments = db.query(Deployment).order_by(Deployment.deployed_at.desc()).all()
    projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse(
        request, "deployments.html",
        {**_ctx(request, db), "active_page": "deployments",
         "deployments": deployments, "projects": projects,
         "success": success, "error": error},
    )


@router.post("/deployments/create")
async def deployment_create(
    request: Request,
    project_id: str = Form(""),
    environment: str = Form("production"),
    version: str = Form(""),
    deployed_by: str = Form(""),
    status: str = Form("success"),
    release_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    pid = int(project_id) if project_id.strip() else None
    deployment = Deployment(
        project_id=pid,
        environment=environment.strip(),
        version=version.strip() or None,
        deployed_by=deployed_by.strip() or user.username,
        status=status.strip(),
        release_notes=release_notes.strip() or None,
    )
    db.add(deployment)
    db.flush()
    project_name = None
    if pid:
        p = db.query(Project).filter(Project.id == pid).first()
        project_name = p.name if p else None
    _log(db, request, user, "create_deployment", "deployment", deployment.id,
         project_name or "N/A", {"env": environment, "version": version})
    db.commit()
    return RedirectResponse("/admin/deployments?success=Deployment+recorded", status_code=302)


@router.post("/deployments/{deployment_id}/delete")
async def deployment_delete(
    deployment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    dep = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if dep:
        _log(db, request, user, "delete_deployment", "deployment", deployment_id)
        db.delete(dep)
        db.commit()
    return RedirectResponse("/admin/deployments?success=Deployment+deleted", status_code=302)


# Secrets Vault

@router.get("/secrets")
async def secrets_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret_list = db.query(Secret).order_by(Secret.created_at.desc()).all()
    projects = db.query(Project).order_by(Project.name).all()
    servers = db.query(Server).order_by(Server.name).all()
    return templates.TemplateResponse(
        request, "secrets.html",
        {**_ctx(request, db), "active_page": "secrets",
         "secrets": secret_list, "projects": projects, "servers": servers,
         "success": success, "error": error},
    )


@router.post("/secrets/create")
async def secret_create(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    value: str = Form(...),
    project_id: str = Form(""),
    rotation_mode: str = Form("manual"),
    rotation_interval_days: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    if not settings.ENCRYPTION_KEY:
        return RedirectResponse("/admin/secrets?error=ENCRYPTION_KEY+not+set+in+.env", status_code=302)
    try:
        encrypted = encrypt_private_key(value.strip())
    except Exception as e:
        return RedirectResponse(f"/admin/secrets?error=Encryption+failed:+{str(e)[:60]}", status_code=302)
    pid = int(project_id) if project_id.strip() else None
    interval = int(rotation_interval_days) if rotation_interval_days.strip() else None
    mode = rotation_mode.strip() if rotation_mode.strip() in ("manual", "auto", "reminder") else "manual"
    next_rotation = compute_next_rotation(interval, datetime.utcnow()) if (mode != "manual" and interval) else None
    secret = Secret(
        name=name.strip(),
        category=category.strip(),
        encrypted_value=encrypted,
        project_id=pid,
        created_by=user.username,
        rotation_mode=mode,
        rotation_interval_days=interval,
        next_rotation_at=next_rotation,
    )
    db.add(secret)
    db.flush()
    _log(db, request, user, "create_secret", "secret", secret.id, secret.name,
         {"category": category})
    db.commit()
    return RedirectResponse("/admin/secrets?success=Secret+stored", status_code=302)


@router.post("/secrets/{secret_id}/rotation-settings")
async def secret_rotation_settings(
    secret_id: int,
    request: Request,
    rotation_mode: str = Form("manual"),
    rotation_interval_days: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        return RedirectResponse("/admin/secrets?error=Secret+not+found", status_code=302)
    mode = rotation_mode.strip() if rotation_mode.strip() in ("manual", "auto", "reminder") else "manual"
    interval = int(rotation_interval_days) if rotation_interval_days.strip() else None
    secret.rotation_mode = mode
    secret.rotation_interval_days = interval
    secret.next_rotation_at = (
        compute_next_rotation(interval, datetime.utcnow()) if (mode != "manual" and interval) else None
    )
    _log(db, request, user, "update_secret_rotation_settings", "secret", secret_id, secret.name,
         {"rotation_mode": mode, "rotation_interval_days": interval})
    db.commit()
    return RedirectResponse("/admin/secrets?success=Rotation+settings+updated", status_code=302)


@router.post("/secrets/{secret_id}/reveal")
async def secret_reveal(
    secret_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        return RedirectResponse("/admin/secrets?error=Secret+not+found", status_code=302)
    try:
        plaintext = decrypt_private_key(secret.encrypted_value)
    except Exception as e:
        return RedirectResponse(f"/admin/secrets?error=Decrypt+failed:+{str(e)[:60]}", status_code=302)
    _log(db, request, user, "reveal_secret", "secret", secret_id, secret.name)
    db.commit()
    return templates.TemplateResponse(
        request, "secrets.html",
        {
            **_ctx(request, db),
            "active_page": "secrets",
            "secrets": db.query(Secret).order_by(Secret.created_at.desc()).all(),
            "projects": db.query(Project).order_by(Project.name).all(),
            "servers": db.query(Server).order_by(Server.name).all(),
            "revealed_id": secret_id,
            "revealed_value": plaintext,
            "success": "",
            "error": "",
        },
    )


@router.post("/secrets/{secret_id}/rotate")
async def secret_rotate(
    secret_id: int,
    request: Request,
    new_value: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        return RedirectResponse("/admin/secrets?error=Secret+not+found", status_code=302)
    value = new_value.strip()
    if not value:
        if secret.rotation_mode != "auto":
            return RedirectResponse(
                "/admin/secrets?error=A+new+value+is+required+for+manual/reminder+secrets",
                status_code=302,
            )
        value = generate_random_value()
    try:
        rotate_secret_core(db, secret, value, actor_name=user.username)
        push_results = push_secret_to_targets(db, secret, value)
        secret.last_rotation_status = "success"
        secret.last_rotation_error = None
        _log(db, request, user, "rotate_secret", "secret", secret_id, secret.name)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(f"/admin/secrets?error=Rotation+failed:+{str(e)[:60]}", status_code=302)
    failed = [r for r in push_results if r.get("status") == "failed"]
    msg = "Secret+rotated"
    if push_results:
        msg += f"+%C2%B7+{len(push_results) - len(failed)}+target(s)+pushed"
        if failed:
            msg += f"%2C+{len(failed)}+failed"
    return RedirectResponse(f"/admin/secrets?success={msg}", status_code=302)


@router.post("/secrets/{secret_id}/delete")
async def secret_delete(
    secret_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if secret:
        blocking = db.query(Server).filter(Server.ssh_key_secret_id == secret_id).first()
        if blocking:
            return RedirectResponse(
                f"/admin/secrets?error=Secret+is+used+as+the+SSH+key+for+server+'{blocking.name}'+-+unlink+it+first",
                status_code=302,
            )
        _log(db, request, user, "delete_secret", "secret", secret_id, secret.name)
        db.delete(secret)
        db.commit()
    return RedirectResponse("/admin/secrets?success=Secret+deleted", status_code=302)


# VPS Sync Targets

@router.post("/secrets/{secret_id}/targets/create")
async def secret_target_create(
    secret_id: int,
    request: Request,
    server_id: int = Form(...),
    remote_path: str = Form(""),
    remote_key: str = Form(""),
    go_live: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        return RedirectResponse("/admin/secrets?error=Secret+not+found", status_code=302)
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        return RedirectResponse("/admin/secrets?error=Server+not+found", status_code=302)
    target = SecretVpsTarget(
        secret_id=secret_id,
        server_id=server_id,
        remote_path=remote_path.strip() or None,
        remote_key=remote_key.strip() or None,
        dry_run=(go_live != "on"),
    )
    db.add(target)
    db.flush()
    _log(db, request, user, "create_vps_target", "secret", secret_id, secret.name,
         {"server": server.name})
    db.commit()
    return RedirectResponse("/admin/secrets?success=VPS+target+added", status_code=302)


@router.post("/vps-targets/{target_id}/delete")
async def vps_target_delete(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if target:
        _log(db, request, user, "delete_vps_target", "secret", target.secret_id)
        db.delete(target)
        db.commit()
    return RedirectResponse("/admin/secrets?success=VPS+target+removed", status_code=302)


@router.post("/vps-targets/{target_id}/push")
async def vps_target_push(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target:
        return RedirectResponse("/admin/secrets?error=Target+not+found", status_code=302)
    secret = target.secret
    try:
        plaintext = decrypt_private_key(secret.encrypted_value)
        result = push_to_single_target(target, secret.name, plaintext)
        _log(db, request, user, "push_vps_target", "secret", secret.id, secret.name)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(f"/admin/secrets?error=Push+failed:+{str(e)[:80]}", status_code=302)
    if result.get("status") == "failed":
        return RedirectResponse(f"/admin/secrets?error=Push+failed:+{str(result.get('detail'))[:80]}", status_code=302)
    return RedirectResponse("/admin/secrets?success=Pushed+to+server", status_code=302)


@router.post("/vps-targets/{target_id}/test")
async def vps_target_test(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    target = db.query(SecretVpsTarget).filter(SecretVpsTarget.id == target_id).first()
    if not target or not target.server:
        return RedirectResponse("/admin/secrets?error=Target+not+found", status_code=302)
    server = target.server
    try:
        if not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Server is missing SSH connection details")
        private_key_pem = decrypt_private_key(server.ssh_key_secret.encrypted_value)
        ssh_sync.test_connection(server.ssh_host, server.ssh_port or 22, server.ssh_username, private_key_pem)
        _log(db, request, user, "test_vps_target", "server", server.id, server.name)
        db.commit()
    except Exception as e:
        return RedirectResponse(f"/admin/secrets?error=Connection+failed:+{str(e)[:80]}", status_code=302)
    return RedirectResponse("/admin/secrets?success=Connection+OK", status_code=302)


# Audit Logs

@router.get("/audit-logs")
async def audit_logs_list(
    request: Request,
    q: str = "",
    resource: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    query = db.query(AuditLog)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            (AuditLog.actor_name.ilike(like)) |
            (AuditLog.action.ilike(like)) |
            (AuditLog.resource_name.ilike(like))
        )
    if resource.strip():
        query = query.filter(AuditLog.resource_type == resource.strip())
    logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return templates.TemplateResponse(
        request, "audit_logs.html",
        {**_ctx(request, db), "active_page": "audit_logs",
         "logs": logs, "q": q, "resource": resource},
    )


# Users

@router.get("/users")
async def users_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    users = db.query(AdminUser).order_by(AdminUser.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "users.html",
        {**_ctx(request, db), "active_page": "users",
         "users": users, "success": success, "error": error},
    )


@router.post("/users/create")
async def user_create(
    request: Request,
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    role: str = Form("SUPPORT"),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    if db.query(AdminUser).filter(AdminUser.username == username.strip()).first():
        return RedirectResponse("/admin/users?error=Username+already+exists", status_code=302)
    new_user = AdminUser(
        username=username.strip(),
        email=email.strip() or None,
        password_hash=hash_password(password),
        role=role.strip(),
        status="active",
    )
    db.add(new_user)
    db.flush()
    _log(db, request, user, "create_user", "user", new_user.id, new_user.username, {"role": role})
    db.commit()
    return RedirectResponse("/admin/users?success=User+created", status_code=302)


@router.post("/users/{user_id}/update-role")
async def user_update_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    target = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if target:
        target.role = role
        _log(db, request, user, "update_user_role", "user", user_id, target.username, {"new_role": role})
        db.commit()
    return RedirectResponse("/admin/users?success=Role+updated", status_code=302)


@router.post("/users/{user_id}/toggle-status")
async def user_toggle_status(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    if user_id == user.id:
        return RedirectResponse("/admin/users?error=Cannot+change+your+own+status", status_code=302)
    target = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if target:
        target.status = "suspended" if target.status == "active" else "active"
        _log(db, request, user, "toggle_user_status", "user", user_id, target.username,
             {"new_status": target.status})
        db.commit()
    return RedirectResponse("/admin/users?success=User+status+updated", status_code=302)


@router.post("/users/{user_id}/reset-password")
async def user_reset_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    target = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if target:
        target.password_hash = hash_password(new_password)
        _log(db, request, user, "reset_password", "user", user_id, target.username)
        db.commit()
    return RedirectResponse("/admin/users?success=Password+reset", status_code=302)


# Domains

@router.get("/domains")
async def domains_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    from datetime import date
    today = date.today()
    domains = db.query(Domain).order_by(Domain.domain).all()
    projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse(
        request, "domains.html",
        {**_ctx(request, db), "active_page": "domains",
         "domains": domains, "projects": projects, "today": today,
         "success": success, "error": error},
    )


@router.post("/domains/create")
async def domain_create(
    request: Request,
    domain: str = Form(...),
    project_id: str = Form(""),
    registrar: str = Form(""),
    dns_provider: str = Form(""),
    expiry_date: str = Form(""),
    auto_renew: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    from datetime import date
    exp = None
    if expiry_date.strip():
        try:
            exp = date.fromisoformat(expiry_date.strip())
        except ValueError:
            pass
    pid = int(project_id) if project_id.strip() else None
    d = Domain(
        domain=domain.strip().lower(),
        project_id=pid,
        registrar=registrar.strip() or None,
        dns_provider=dns_provider.strip() or None,
        expiry_date=exp,
        auto_renew=bool(auto_renew),
        notes=notes.strip() or None,
    )
    db.add(d)
    db.flush()
    _log(db, request, user, "create_domain", "domain", d.id, d.domain)
    db.commit()
    return RedirectResponse("/admin/domains?success=Domain+added", status_code=302)


@router.post("/domains/{domain_id}/update")
async def domain_update(
    domain_id: int,
    request: Request,
    registrar: str = Form(""),
    dns_provider: str = Form(""),
    expiry_date: str = Form(""),
    auto_renew: str = Form(""),
    notes: str = Form(""),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    from datetime import date
    d = db.query(Domain).filter(Domain.id == domain_id).first()
    if not d:
        return RedirectResponse("/admin/domains?error=Domain+not+found", status_code=302)
    if expiry_date.strip():
        try:
            d.expiry_date = date.fromisoformat(expiry_date.strip())
        except ValueError:
            pass
    d.registrar = registrar.strip() or None
    d.dns_provider = dns_provider.strip() or None
    d.auto_renew = bool(auto_renew)
    d.notes = notes.strip() or None
    d.status = status.strip()
    _log(db, request, user, "update_domain", "domain", domain_id, d.domain)
    db.commit()
    return RedirectResponse("/admin/domains?success=Domain+updated", status_code=302)


@router.post("/domains/{domain_id}/delete")
async def domain_delete(
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    d = db.query(Domain).filter(Domain.id == domain_id).first()
    if d:
        _log(db, request, user, "delete_domain", "domain", domain_id, d.domain)
        db.delete(d)
        db.commit()
    return RedirectResponse("/admin/domains?success=Domain+deleted", status_code=302)


# Integrations

@router.get("/integrations")
async def integrations_list(
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    integrations = db.query(Integration).order_by(Integration.service).all()
    projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse(
        request, "integrations.html",
        {**_ctx(request, db), "active_page": "integrations",
         "integrations": integrations, "projects": projects,
         "success": success, "error": error},
    )


@router.post("/integrations/create")
async def integration_create(
    request: Request,
    service: str = Form(...),
    account: str = Form(""),
    project_id: str = Form(""),
    related_secrets: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    pid = int(project_id) if project_id.strip() else None
    ig = Integration(
        service=service.strip(),
        account=account.strip() or None,
        project_id=pid,
        related_secrets=related_secrets.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(ig)
    db.flush()
    _log(db, request, user, "create_integration", "integration", ig.id, ig.service)
    db.commit()
    return RedirectResponse("/admin/integrations?success=Integration+added", status_code=302)


@router.post("/integrations/{integration_id}/delete")
async def integration_delete(
    integration_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    ig = db.query(Integration).filter(Integration.id == integration_id).first()
    if ig:
        _log(db, request, user, "delete_integration", "integration", integration_id, ig.service)
        db.delete(ig)
        db.commit()
    return RedirectResponse("/admin/integrations?success=Integration+deleted", status_code=302)


# Notes

@router.get("/notes")
async def notes_list(
    request: Request,
    project_id: str = "",
    q: str = "",
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    query = db.query(Note)
    if project_id.strip():
        query = query.filter(Note.project_id == int(project_id))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            (Note.title.ilike(like)) | (Note.content.ilike(like)) | (Note.tags.ilike(like))
        )
    notes = query.order_by(Note.updated_at.desc()).all()
    projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse(
        request, "notes.html",
        {**_ctx(request, db), "active_page": "notes",
         "notes": notes, "projects": projects, "q": q,
         "filter_project_id": project_id,
         "success": success, "error": error},
    )


@router.post("/notes/create")
async def note_create(
    request: Request,
    title: str = Form(...),
    content: str = Form(""),
    project_id: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    pid = int(project_id) if project_id.strip() else None
    note = Note(
        title=title.strip(),
        content=content.strip(),
        project_id=pid,
        tags=tags.strip() or None,
        created_by=user.username,
    )
    db.add(note)
    db.flush()
    _log(db, request, user, "create_note", "note", note.id, note.title)
    db.commit()
    return RedirectResponse(f"/admin/notes/{note.id}/edit?success=Note+created", status_code=302)


@router.get("/notes/{note_id}/edit")
async def note_edit_page(
    note_id: int,
    request: Request,
    success: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        return RedirectResponse("/admin/notes?error=Note+not+found", status_code=302)
    projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse(
        request, "note_edit.html",
        {**_ctx(request, db), "active_page": "notes",
         "note": note, "projects": projects, "success": success, "error": error},
    )


@router.post("/notes/{note_id}/update")
async def note_update(
    note_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(""),
    project_id: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        return RedirectResponse("/admin/notes?error=Note+not+found", status_code=302)
    note.title = title.strip()
    note.content = content.strip()
    note.project_id = int(project_id) if project_id.strip() else None
    note.tags = tags.strip() or None
    note.updated_at = datetime.utcnow()
    _log(db, request, user, "update_note", "note", note_id, note.title)
    db.commit()
    return RedirectResponse(f"/admin/notes/{note_id}/edit?success=Note+saved", status_code=302)


@router.post("/notes/{note_id}/delete")
async def note_delete(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    note = db.query(Note).filter(Note.id == note_id).first()
    if note:
        _log(db, request, user, "delete_note", "note", note_id, note.title)
        db.delete(note)
        db.commit()
    return RedirectResponse("/admin/notes?success=Note+deleted", status_code=302)


# Secret Version History

@router.get("/secrets/{secret_id}/versions")
async def secret_versions(
    secret_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        return RedirectResponse("/admin/secrets?error=Secret+not+found", status_code=302)
    versions = (
        db.query(SecretVersion)
        .filter(SecretVersion.secret_id == secret_id)
        .order_by(SecretVersion.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request, "secret_versions.html",
        {**_ctx(request, db), "active_page": "secrets",
         "secret": secret, "versions": versions},
    )


@router.post("/secrets/{secret_id}/versions/{version_id}/restore")
async def secret_version_restore(
    secret_id: int,
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    version = db.query(SecretVersion).filter(
        SecretVersion.id == version_id, SecretVersion.secret_id == secret_id
    ).first()
    if not secret or not version:
        return RedirectResponse(f"/admin/secrets/{secret_id}/versions?error=Not+found", status_code=302)
    # Save current value as a new version before overwriting
    db.add(SecretVersion(
        secret_id=secret_id,
        encrypted_value=secret.encrypted_value,
        rotated_by=f"{user.username} (before restore)",
    ))
    secret.encrypted_value = version.encrypted_value
    secret.rotated_at = datetime.utcnow()
    _log(db, request, user, "restore_secret_version", "secret", secret_id, secret.name,
         {"version_id": version_id})
    db.commit()
    return RedirectResponse(f"/admin/secrets/{secret_id}/versions?success=Version+restored", status_code=302)


# Search

@router.get("/search")
async def search(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    results = {}
    if q.strip():
        like = f"%{q.strip()}%"
        results["projects"] = db.query(Project).filter(
            (Project.name.ilike(like)) | (Project.slug.ilike(like)) | (Project.description.ilike(like))
        ).limit(10).all()
        results["customers"] = db.query(Customer).filter(
            (Customer.name.ilike(like)) | (Customer.company_name.ilike(like)) | (Customer.email.ilike(like))
        ).limit(10).all()
        results["secrets"] = db.query(Secret).filter(
            (Secret.name.ilike(like)) | (Secret.category.ilike(like))
        ).limit(10).all()
        results["domains"] = db.query(Domain).filter(
            Domain.domain.ilike(like)
        ).limit(10).all()
        results["servers"] = db.query(Server).filter(
            (Server.name.ilike(like)) | (Server.provider.ilike(like)) | (Server.ip_address.ilike(like))
        ).limit(10).all()
        results["integrations"] = db.query(Integration).filter(
            (Integration.service.ilike(like)) | (Integration.account.ilike(like))
        ).limit(10).all()
        results["notes"] = db.query(Note).filter(
            (Note.title.ilike(like)) | (Note.content.ilike(like)) | (Note.tags.ilike(like))
        ).limit(10).all()
    return templates.TemplateResponse(
        request, "search.html",
        {**_ctx(request, db), "active_page": "search",
         "q": q, "results": results},
    )


# Notifications

@router.post("/notifications/{notif_id}/read")
async def notification_read(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, redir = _guard(request, db)
    if redir:
        return redir
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.recipient_id == user.id,
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return RedirectResponse(request.headers.get("referer", "/admin/dashboard"), status_code=302)
