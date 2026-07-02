from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, AdminUser
from ..auth import get_current_user, log_action, get_client_ip
from ..crypto import generate_key_pair, derive_public_key, encrypt_private_key
from ..config import settings
from ..rotation import restart_project
from ..schemas import (
    ProjectOut, ProjectCreate, ProjectUpdate, ProjectRestartSettings,
    ReimportKeyRequest, MessageResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    if not settings.ENCRYPTION_KEY:
        raise HTTPException(status_code=400, detail="ENCRYPTION_KEY not set on server")

    slug = body.slug.strip().lower().replace(" ", "-")
    if db.query(Project).filter(Project.slug == slug).first():
        raise HTTPException(status_code=400, detail=f'Slug "{slug}" already exists')

    try:
        if body.import_private_key.strip():
            private_b64 = body.import_private_key.strip()
            public_b64 = derive_public_key(private_b64)
        else:
            public_b64, private_b64 = generate_key_pair()
        private_enc = encrypt_private_key(private_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Key error: {str(e)[:80]}")

    project = Project(
        name=body.name.strip(),
        slug=slug,
        description=body.description.strip(),
        deep_link_scheme=body.deep_link_scheme.strip(),
        public_key_b64=public_b64,
        private_key_enc=private_enc,
        type=body.type.strip() or None,
        status=body.status.strip() or "Development",
        version=body.version.strip() or None,
    )
    db.add(project)
    db.flush()
    log_action(db, current_user, "create_project", get_client_ip(request), "project", project.id, project.name)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.name = body.name.strip()
    project.description = body.description.strip()
    project.type = body.type.strip() or None
    project.status = body.status.strip() or project.status
    project.version = body.version.strip() or None
    log_action(db, current_user, "update_project", get_client_ip(request), "project", project_id, project.name)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/reimport-key", response_model=ProjectOut)
async def reimport_key(
    project_id: int,
    body: ReimportKeyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        public_b64 = derive_public_key(body.private_key.strip())
        project.public_key_b64 = public_b64
        project.private_key_enc = encrypt_private_key(body.private_key.strip())
        log_action(db, current_user, "reimport_key", get_client_ip(request), "project", project_id, project.name)
        db.commit()
        db.refresh(project)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Key import failed: {str(e)[:80]}")
    return project


@router.patch("/{project_id}/restart-settings", response_model=ProjectOut)
async def update_restart_settings(
    project_id: int,
    body: ProjectRestartSettings,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.restart_server_id = body.restart_server_id
    project.restart_command = body.restart_command.strip() or None
    project.restart_dry_run = body.restart_dry_run
    log_action(db, current_user, "update_restart_settings", get_client_ip(request), "project", project_id, project.name)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/restart", response_model=ProjectOut)
async def do_restart_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = restart_project(db, project)
    log_action(db, current_user, "restart_project", get_client_ip(request), "project", project_id, project.name, {"status": result["status"]})
    db.commit()
    db.refresh(project)
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=f"Restart failed: {result['output'][:200]}")
    return project


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    log_action(db, current_user, "delete_project", get_client_ip(request), "project", project_id, project.name)
    db.delete(project)
    db.commit()
    return {"message": "Project deleted"}
