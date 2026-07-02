from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


# Shared brief types

class ProjectBrief(BaseModel):
    id: int
    name: str
    slug: str
    model_config = ConfigDict(from_attributes=True)


class CustomerBrief(BaseModel):
    id: int
    name: str
    company_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# Auth

class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    status: str
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


# Dashboard

class RecentToken(BaseModel):
    id: int
    license_number: str
    status: str
    created_at: datetime
    project: ProjectBrief
    customer: CustomerBrief
    model_config = ConfigDict(from_attributes=True)


class RecentLicense(BaseModel):
    id: int
    license_number: str
    computer_id: str
    is_active: bool
    activated_at: datetime
    project: ProjectBrief
    customer: CustomerBrief
    model_config = ConfigDict(from_attributes=True)


class AuditLogBrief(BaseModel):
    id: int
    actor_name: str
    action: str
    resource_type: Optional[str] = None
    resource_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DashboardStats(BaseModel):
    total_projects: int
    total_customers: int
    pending_tokens: int
    active_licenses: int
    total_devices: int
    online_servers: int
    total_servers: int
    recent_tokens: list[RecentToken]
    recent_licenses: list[RecentLicense]
    recent_audit: list[AuditLogBrief]


# Projects

class ProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    deep_link_scheme: str
    public_key_b64: str
    type: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None
    repository_url: Optional[str] = None
    owner: Optional[str] = None
    created_at: datetime
    restart_server_id: Optional[int] = None
    restart_command: Optional[str] = None
    restart_dry_run: bool = True
    last_restart_at: Optional[datetime] = None
    last_restart_status: Optional[str] = None
    last_restart_output: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ProjectRestartSettings(BaseModel):
    restart_server_id: Optional[int] = None
    restart_command: str = ""
    restart_dry_run: bool = True


class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: str = ""
    deep_link_scheme: str
    type: str = ""
    status: str = "Development"
    version: str = ""
    import_private_key: str = ""


class ProjectUpdate(BaseModel):
    name: str
    description: str = ""
    type: str = ""
    status: str = ""
    version: str = ""


class ReimportKeyRequest(BaseModel):
    private_key: str


# Customers

class CustomerOut(BaseModel):
    id: int
    name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CustomerCreate(BaseModel):
    name: str
    company_name: str = ""
    email: str = ""
    phone: str = ""
    country: str = ""
    notes: str = ""


class CustomerUpdate(BaseModel):
    name: str
    company_name: str = ""
    email: str = ""
    phone: str = ""
    country: str = ""
    notes: str = ""
    status: str = "active"


# Activation Tokens

class TokenOut(BaseModel):
    id: int
    token: str
    project_id: int
    customer_id: int
    license_number: str
    license_type: str
    status: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    used_at: Optional[datetime] = None
    project: ProjectBrief
    customer: CustomerBrief
    activation_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TokenCreate(BaseModel):
    project_id: int
    customer_id: int
    license_number: str
    license_type: str = "lifetime"
    expires_days: Optional[int] = None


# Licenses

class LicenseOut(BaseModel):
    id: int
    license_number: str
    computer_id: str
    is_active: bool
    activated_at: datetime
    deactivated_at: Optional[datetime] = None
    project: ProjectBrief
    customer: CustomerBrief
    model_config = ConfigDict(from_attributes=True)


# Devices

class DeviceOut(BaseModel):
    id: int
    fingerprint: str
    hostname: Optional[str] = None
    os: Optional[str] = None
    app_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    status: str
    blocked_at: Optional[datetime] = None
    created_at: datetime
    customer: Optional[CustomerBrief] = None
    model_config = ConfigDict(from_attributes=True)


# Servers

class ServerOut(BaseModel):
    id: int
    name: str
    provider: Optional[str] = None
    ip_address: Optional[str] = None
    cpu: Optional[str] = None
    ram: Optional[str] = None
    storage: Optional[str] = None
    operating_system: Optional[str] = None
    purpose: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    ssh_username: Optional[str] = None
    ssh_key_secret_id: Optional[int] = None
    default_env_path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ServerCreate(BaseModel):
    name: str
    provider: str = ""
    ip_address: str = ""
    cpu: str = ""
    ram: str = ""
    storage: str = ""
    operating_system: str = ""
    purpose: str = ""
    status: str = "running"
    notes: str = ""
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_key_secret_id: Optional[int] = None
    default_env_path: str = ".env"


class ServerUpdate(BaseModel):
    name: str
    provider: str = ""
    ip_address: str = ""
    cpu: str = ""
    ram: str = ""
    storage: str = ""
    operating_system: str = ""
    purpose: str = ""
    notes: str = ""
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_key_secret_id: Optional[int] = None
    default_env_path: str = ".env"


class ServerUpdateStatus(BaseModel):
    status: str


# Deployments

class DeploymentOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    environment: str
    version: Optional[str] = None
    deployed_by: Optional[str] = None
    status: str
    release_notes: Optional[str] = None
    deployed_at: datetime
    project: Optional[ProjectBrief] = None
    model_config = ConfigDict(from_attributes=True)


class DeploymentCreate(BaseModel):
    project_id: Optional[int] = None
    environment: str = "production"
    version: str = ""
    deployed_by: str = ""
    status: str = "success"
    release_notes: str = ""


# Secrets

class SecretOut(BaseModel):
    id: int
    name: str
    category: str
    project_id: Optional[int] = None
    environment: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    rotated_at: Optional[datetime] = None
    created_at: datetime
    project: Optional[ProjectBrief] = None
    rotation_mode: str = "manual"
    rotation_interval_days: Optional[int] = None
    next_rotation_at: Optional[datetime] = None
    last_rotation_status: Optional[str] = None
    last_rotation_error: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class SecretCreate(BaseModel):
    name: str
    category: str
    value: str
    project_id: Optional[int] = None
    environment: str = ""
    description: str = ""
    rotation_mode: str = "manual"
    rotation_interval_days: Optional[int] = None


class SecretRotationSettings(BaseModel):
    rotation_mode: str = "manual"
    rotation_interval_days: Optional[int] = None


class SecretRotate(BaseModel):
    new_value: Optional[str] = None


class SecretRevealed(BaseModel):
    id: int
    name: str
    value: str


class SecretVersionOut(BaseModel):
    id: int
    secret_id: int
    rotated_by: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# VPS Sync Targets

class VpsTargetOut(BaseModel):
    id: int
    secret_id: int
    server_id: int
    remote_path: Optional[str] = None
    remote_key: Optional[str] = None
    dry_run: bool = True
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class VpsTargetCreate(BaseModel):
    secret_id: int
    server_id: int
    remote_path: str = ""
    remote_key: str = ""
    dry_run: bool = True


class VpsTargetUpdate(BaseModel):
    remote_path: str = ""
    remote_key: str = ""
    dry_run: bool = True


# Domains

class DomainOut(BaseModel):
    id: int
    domain: str
    project_id: Optional[int] = None
    registrar: Optional[str] = None
    dns_provider: Optional[str] = None
    expiry_date: Optional[date] = None
    auto_renew: bool
    status: str
    notes: Optional[str] = None
    created_at: datetime
    project: Optional[ProjectBrief] = None
    days_until_expiry: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class DomainCreate(BaseModel):
    domain: str
    project_id: Optional[int] = None
    registrar: str = ""
    dns_provider: str = ""
    expiry_date: Optional[date] = None
    auto_renew: bool = False
    notes: str = ""


class DomainUpdate(BaseModel):
    registrar: str = ""
    dns_provider: str = ""
    expiry_date: Optional[date] = None
    auto_renew: bool = False
    notes: str = ""
    status: str = "active"


# Integrations

class IntegrationOut(BaseModel):
    id: int
    service: str
    account: Optional[str] = None
    project_id: Optional[int] = None
    related_secrets: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime
    project: Optional[ProjectBrief] = None
    model_config = ConfigDict(from_attributes=True)


class IntegrationCreate(BaseModel):
    service: str
    account: str = ""
    project_id: Optional[int] = None
    related_secrets: str = ""
    notes: str = ""


# Notes

class NoteOut(BaseModel):
    id: int
    title: str
    content: str
    project_id: Optional[int] = None
    tags: Optional[str] = None
    created_by: Optional[str] = None
    updated_at: datetime
    created_at: datetime
    project: Optional[ProjectBrief] = None
    model_config = ConfigDict(from_attributes=True)


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    project_id: Optional[int] = None
    tags: str = ""


class NoteUpdate(BaseModel):
    title: str
    content: str = ""
    project_id: Optional[int] = None
    tags: str = ""


# Users

class AdminUserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str
    email: str = ""
    password: str
    role: str = "SUPPORT"


class UserUpdateRole(BaseModel):
    role: str


class UserResetPassword(BaseModel):
    new_password: str


# Audit Logs

class AuditLogOut(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_name: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    extra_data: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Notifications

class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Search

class SearchResults(BaseModel):
    projects: list[ProjectOut] = []
    customers: list[CustomerOut] = []
    secrets: list[SecretOut] = []
    domains: list[DomainOut] = []
    servers: list[ServerOut] = []
    integrations: list[IntegrationOut] = []
    notes: list[NoteOut] = []


# Generic

class MessageResponse(BaseModel):
    message: str
