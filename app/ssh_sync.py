import io
import uuid

import paramiko


class SSHSyncError(Exception):
    pass


def _replace_env_line(content: str, key: str, value: str) -> str:
    """Return .env content with KEY set to value, preserving every other line verbatim.
    Only matches a real assignment line (KEY=...), never a commented-out line (#KEY=...).
    Appends a new KEY=value line if the key isn't present.
    """
    lines = content.splitlines()
    prefix = f"{key}="
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(prefix):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    return "\n".join(new_lines) + "\n"


def _load_private_key(private_key_pem: str):
    last_exc = None
    for key_cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(private_key_pem))
        except Exception as exc:
            last_exc = exc
    raise SSHSyncError(f"Could not load private key with any supported algorithm: {last_exc}")


def _connect(host: str, port: int, username: str, private_key_pem: str) -> paramiko.SSHClient:
    pkey = _load_private_key(private_key_pem)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=username, pkey=pkey, timeout=10)
    except Exception as exc:
        raise SSHSyncError(f"SSH connection to {username}@{host}:{port} failed: {exc}") from exc
    return client


def test_connection(host: str, port: int, username: str, private_key_pem: str) -> bool:
    client = _connect(host, port, username, private_key_pem)
    try:
        client.exec_command("true", timeout=10)
    finally:
        client.close()
    return True


def run_command(
    host: str, port: int, username: str, private_key_pem: str,
    command: str, timeout: int = 30, dry_run: bool = True,
) -> dict:
    if dry_run:
        return {"dry_run": True, "action": f"would run on {host}:{port}: {command}"}

    client = _connect(host, port, username, private_key_pem)
    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise SSHSyncError(f"Command failed on {host}: {exc}") from exc
    finally:
        client.close()

    return {"dry_run": False, "exit_code": exit_code, "stdout": out[:4000], "stderr": err[:4000]}


def upsert_env_line(
    host: str, port: int, username: str, private_key_pem: str,
    remote_path: str, key: str, value: str, dry_run: bool = True,
) -> dict:
    if dry_run:
        return {"dry_run": True, "action": f"would set {key} in {remote_path} on {host}:{port}"}

    client = _connect(host, port, username, private_key_pem)
    try:
        sftp = client.open_sftp()
        try:
            file_mode = None
            try:
                with sftp.open(remote_path, "r") as f:
                    old_content = f.read().decode("utf-8", errors="replace")
                file_mode = sftp.stat(remote_path).st_mode
            except FileNotFoundError:
                old_content = ""

            new_content = _replace_env_line(old_content, key, value)

            tmp_path = f"{remote_path}.tmp-{uuid.uuid4().hex}"
            with sftp.open(tmp_path, "w") as f:
                f.write(new_content.encode("utf-8"))
                f.flush()

            if file_mode is not None:
                sftp.chmod(tmp_path, file_mode & 0o777)

            sftp.posix_rename(tmp_path, remote_path)
        finally:
            sftp.close()
    except SSHSyncError:
        raise
    except Exception as exc:
        raise SSHSyncError(f"Failed to update {remote_path} on {host}: {exc}") from exc
    finally:
        client.close()

    return {"dry_run": False, "action": f"set {key} in {remote_path} on {host}:{port}"}
