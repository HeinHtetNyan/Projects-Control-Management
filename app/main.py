from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text

from .config import settings
from .database import engine, Base, SessionLocal
from .models import AdminUser
from .auth import hash_password
from .routers import activation, admin

app = FastAPI(title=settings.APP_NAME, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, max_age=28800)

app.include_router(activation.router)
app.include_router(admin.router)


def _add_column_if_not_exists(conn, table: str, column: str, col_def: str):
    result = conn.execute(text(
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    if not result.fetchone():
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))


@app.on_event("startup")
def on_startup():
    # Create all tables (new tables only — existing ones are untouched)
    Base.metadata.create_all(bind=engine)

    # Safely add new columns to existing tables
    with engine.begin() as conn:
        # admin_users
        _add_column_if_not_exists(conn, "admin_users", "email", "VARCHAR(255)")
        _add_column_if_not_exists(conn, "admin_users", "role", "VARCHAR(50) NOT NULL DEFAULT 'ADMIN'")
        _add_column_if_not_exists(conn, "admin_users", "status", "VARCHAR(20) NOT NULL DEFAULT 'active'")

        # projects
        _add_column_if_not_exists(conn, "projects", "type", "VARCHAR(50)")
        _add_column_if_not_exists(conn, "projects", "status", "VARCHAR(50) DEFAULT 'Development'")
        _add_column_if_not_exists(conn, "projects", "version", "VARCHAR(50)")
        _add_column_if_not_exists(conn, "projects", "repository_url", "VARCHAR(500)")
        _add_column_if_not_exists(conn, "projects", "owner", "VARCHAR(255)")

        # customers
        _add_column_if_not_exists(conn, "customers", "company_name", "VARCHAR(255)")
        _add_column_if_not_exists(conn, "customers", "country", "VARCHAR(100)")
        _add_column_if_not_exists(conn, "customers", "status", "VARCHAR(20) NOT NULL DEFAULT 'active'")

        # secrets
        _add_column_if_not_exists(conn, "secrets", "environment", "VARCHAR(50)")
        _add_column_if_not_exists(conn, "secrets", "description", "TEXT")

        # servers
        _add_column_if_not_exists(conn, "servers", "purpose", "VARCHAR(255)")
        _add_column_if_not_exists(conn, "servers", "ssh_host", "VARCHAR(255)")
        _add_column_if_not_exists(conn, "servers", "ssh_port", "INTEGER NOT NULL DEFAULT 22")
        _add_column_if_not_exists(conn, "servers", "ssh_username", "VARCHAR(100)")
        _add_column_if_not_exists(conn, "servers", "ssh_key_secret_id", "INTEGER REFERENCES secrets(id)")
        _add_column_if_not_exists(conn, "servers", "default_env_path", "VARCHAR(500) DEFAULT '.env'")

        # secrets — rotation
        _add_column_if_not_exists(conn, "secrets", "rotation_mode", "VARCHAR(20) NOT NULL DEFAULT 'manual'")
        _add_column_if_not_exists(conn, "secrets", "rotation_interval_days", "INTEGER")
        _add_column_if_not_exists(conn, "secrets", "next_rotation_at", "TIMESTAMP")
        _add_column_if_not_exists(conn, "secrets", "last_rotation_status", "VARCHAR(20)")
        _add_column_if_not_exists(conn, "secrets", "last_rotation_error", "TEXT")

        _add_column_if_not_exists(conn, "projects", "restart_server_id", "INTEGER REFERENCES servers(id)")
        _add_column_if_not_exists(conn, "projects", "restart_command", "TEXT")
        _add_column_if_not_exists(conn, "projects", "restart_dry_run", "BOOLEAN NOT NULL DEFAULT true")
        _add_column_if_not_exists(conn, "projects", "last_restart_at", "TIMESTAMP")
        _add_column_if_not_exists(conn, "projects", "last_restart_status", "VARCHAR(20)")
        _add_column_if_not_exists(conn, "projects", "last_restart_output", "TEXT")

    # Bootstrap first admin user
    db = SessionLocal()
    try:
        if db.query(AdminUser).count() == 0 and settings.ADMIN_PASSWORD not in ("admin", "changeme"):
            db.add(AdminUser(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="SUPER_OWNER",
                status="active",
            ))
            db.commit()
    finally:
        db.close()


@app.get("/")
async def root():
    return RedirectResponse("/admin/dashboard", status_code=302)
