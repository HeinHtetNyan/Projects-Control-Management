from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Date
)
from sqlalchemy.orm import relationship
from .database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="ADMIN")
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    notifications = relationship("Notification", back_populates="recipient", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    deep_link_scheme = Column(String(100), nullable=False)
    public_key_b64 = Column(Text, nullable=False)
    private_key_enc = Column(Text, nullable=False)
    type = Column(String(50), nullable=True)
    status = Column(String(50), nullable=True, default="Development")
    version = Column(String(50), nullable=True)
    repository_url = Column(String(500), nullable=True)
    owner = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    restart_server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    restart_command = Column(Text, nullable=True)
    restart_dry_run = Column(Boolean, nullable=False, default=True)
    last_restart_at = Column(DateTime, nullable=True)
    last_restart_status = Column(String(20), nullable=True)   # success | failed | dry_run
    last_restart_output = Column(Text, nullable=True)

    tokens = relationship("ActivationToken", back_populates="project")
    licenses = relationship("License", back_populates="project")
    deployments = relationship("Deployment", back_populates="project")
    secrets = relationship("Secret", back_populates="project")
    domains = relationship("Domain", back_populates="project")
    integrations = relationship("Integration", back_populates="project")
    notes = relationship("Note", back_populates="project", cascade="all, delete-orphan")
    restart_server = relationship("Server", foreign_keys=[restart_server_id])


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    email = Column(String(255))
    phone = Column(String(50))
    country = Column(String(100), nullable=True)
    notes = Column(Text)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    tokens = relationship("ActivationToken", back_populates="customer")
    devices = relationship("Device", back_populates="customer")


class ActivationToken(Base):
    __tablename__ = "activation_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(128), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    license_number = Column(String(100), nullable=False)
    license_type = Column(String(50), default="lifetime")
    status = Column(String(20), default="pending", nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="tokens")
    customer = relationship("Customer", back_populates="tokens")
    license = relationship("License", back_populates="token", uselist=False)


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("activation_tokens.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    license_number = Column(String(100), nullable=False)
    computer_id = Column(String(100), nullable=False)
    activated_at = Column(DateTime, default=datetime.utcnow)
    deactivated_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    certificate_json = Column(Text)

    token = relationship("ActivationToken", back_populates="license")
    project = relationship("Project", back_populates="licenses")
    customer = relationship("Customer")
    device = relationship("Device", back_populates="license", uselist=False)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(Integer, ForeignKey("licenses.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    hostname = Column(String(255), nullable=True)
    fingerprint = Column(String(255), nullable=False, unique=True, index=True)
    os = Column(String(100), nullable=True)
    app_version = Column(String(50), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="online")
    blocked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    license = relationship("License", back_populates="device")
    customer = relationship("Customer", back_populates="devices")


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=True)
    ip_address = Column(String(100), nullable=True)
    cpu = Column(String(100), nullable=True)
    ram = Column(String(100), nullable=True)
    storage = Column(String(100), nullable=True)
    operating_system = Column(String(100), nullable=True)
    purpose = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="running")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    ssh_host = Column(String(255), nullable=True)
    ssh_port = Column(Integer, nullable=False, default=22)
    ssh_username = Column(String(100), nullable=True)
    ssh_key_secret_id = Column(Integer, ForeignKey("secrets.id"), nullable=True)
    default_env_path = Column(String(500), nullable=True, default=".env")

    ssh_key_secret = relationship("Secret", foreign_keys=[ssh_key_secret_id])


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    environment = Column(String(50), nullable=False, default="production")
    version = Column(String(100), nullable=True)
    deployed_by = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="success")
    release_notes = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)
    deployed_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="deployments")


class Secret(Base):
    __tablename__ = "secrets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    environment = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=True)
    rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    rotation_mode = Column(String(20), nullable=False, default="manual")   # manual | auto | reminder
    rotation_interval_days = Column(Integer, nullable=True)
    next_rotation_at = Column(DateTime, nullable=True)
    last_rotation_status = Column(String(20), nullable=True)              # success | failed | reminder_sent
    last_rotation_error = Column(Text, nullable=True)

    project = relationship("Project", back_populates="secrets")
    versions = relationship("SecretVersion", back_populates="secret", cascade="all, delete-orphan",
                            order_by="SecretVersion.created_at.desc()")
    vps_targets = relationship("SecretVpsTarget", back_populates="secret", cascade="all, delete-orphan")


class SecretVersion(Base):
    __tablename__ = "secret_versions"

    id = Column(Integer, primary_key=True, index=True)
    secret_id = Column(Integer, ForeignKey("secrets.id"), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    rotated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    secret = relationship("Secret", back_populates="versions")


class SecretVpsTarget(Base):
    __tablename__ = "secret_vps_targets"

    id = Column(Integer, primary_key=True, index=True)
    secret_id = Column(Integer, ForeignKey("secrets.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    remote_path = Column(String(500), nullable=True)    # overrides server.default_env_path if set
    remote_key = Column(String(255), nullable=True)     # overrides secret.name if set
    dry_run = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(20), nullable=True)   # success | failed | dry_run
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    secret = relationship("Secret", back_populates="vps_targets")
    server = relationship("Server")


class Domain(Base):
    __tablename__ = "domains"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False, unique=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    registrar = Column(String(255), nullable=True)
    dns_provider = Column(String(255), nullable=True)
    expiry_date = Column(Date, nullable=True)
    auto_renew = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="domains")


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(100), nullable=False)
    account = Column(String(255), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    related_secrets = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="integrations")


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False, default="")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    tags = Column(String(500), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="notes")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, nullable=True)
    actor_name = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    resource_name = Column(String(255), nullable=True)
    extra_data = Column("metadata", Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="info")
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    recipient = relationship("AdminUser", back_populates="notifications")
