from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ssh_sync
from ..database import get_db
from ..models import Server, AdminUser
from ..auth import get_current_user, log_action, get_client_ip
from ..crypto import decrypt_value
from ..schemas import ServerOut, ServerCreate, ServerUpdate, ServerUpdateStatus, MessageResponse

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("", response_model=list[ServerOut])
async def list_servers(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    return db.query(Server).order_by(Server.created_at.desc()).all()


@router.post("", response_model=ServerOut, status_code=201)
async def create_server(
    body: ServerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    server = Server(
        name=body.name.strip(),
        provider=body.provider.strip() or None,
        ip_address=body.ip_address.strip() or None,
        cpu=body.cpu.strip() or None,
        ram=body.ram.strip() or None,
        storage=body.storage.strip() or None,
        operating_system=body.operating_system.strip() or None,
        purpose=body.purpose.strip() or None,
        status=body.status.strip(),
        notes=body.notes.strip() or None,
        ssh_host=body.ssh_host.strip() or None,
        ssh_port=body.ssh_port or 22,
        ssh_username=body.ssh_username.strip() or None,
        ssh_key_secret_id=body.ssh_key_secret_id,
        default_env_path=body.default_env_path.strip() or ".env",
    )
    db.add(server)
    db.flush()
    log_action(db, current_user, "create_server", get_client_ip(request), "server", server.id, server.name)
    db.commit()
    db.refresh(server)
    return server


@router.patch("/{server_id}", response_model=ServerOut)
async def update_server(
    server_id: int,
    body: ServerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    server.name = body.name.strip()
    server.provider = body.provider.strip() or None
    server.ip_address = body.ip_address.strip() or None
    server.cpu = body.cpu.strip() or None
    server.ram = body.ram.strip() or None
    server.storage = body.storage.strip() or None
    server.operating_system = body.operating_system.strip() or None
    server.purpose = body.purpose.strip() or None
    server.notes = body.notes.strip() or None
    server.ssh_host = body.ssh_host.strip() or None
    server.ssh_port = body.ssh_port or 22
    server.ssh_username = body.ssh_username.strip() or None
    server.ssh_key_secret_id = body.ssh_key_secret_id
    server.default_env_path = body.default_env_path.strip() or ".env"
    log_action(db, current_user, "update_server", get_client_ip(request), "server", server_id, server.name)
    db.commit()
    db.refresh(server)
    return server


@router.post("/{server_id}/test-ssh", response_model=MessageResponse)
async def test_server_ssh(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    try:
        if not server.ssh_host or not server.ssh_username or not server.ssh_key_secret_id:
            raise ssh_sync.SSHSyncError("Server is missing SSH connection details")
        if not server.ssh_key_secret:
            raise ssh_sync.SSHSyncError("Linked SSH key secret was not found")
        private_key_pem = decrypt_value(server.ssh_key_secret.encrypted_value)
        ssh_sync.test_connection(server.ssh_host, server.ssh_port or 22, server.ssh_username, private_key_pem)
        log_action(db, current_user, "test_server_ssh", get_client_ip(request), "server", server_id, server.name)
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)[:120]}")
    return {"message": "Connection OK"}


@router.patch("/{server_id}/status", response_model=ServerOut)
async def update_server_status(
    server_id: int,
    body: ServerUpdateStatus,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    server.status = body.status
    log_action(db, current_user, "update_server_status", get_client_ip(request), "server", server_id, server.name, {"status": body.status})
    db.commit()
    db.refresh(server)
    return server


@router.delete("/{server_id}", response_model=MessageResponse)
async def delete_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    log_action(db, current_user, "delete_server", get_client_ip(request), "server", server_id, server.name)
    db.delete(server)
    db.commit()
    return {"message": "Server deleted"}
