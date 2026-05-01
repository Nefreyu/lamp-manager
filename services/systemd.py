import os
import subprocess
import tempfile
from pathlib import Path
from config.dev import DEV_MODE, SIMULATE_NOT_INSTALLED

SERVICES = [
    {"id": "apache2",    "label": "Apache2",     "optional": False, "binary": "/usr/sbin/apache2",    "url": "http://localhost"},
    {"id": "mysql",      "label": "MySQL",        "optional": False, "binary": "/usr/sbin/mysqld"},
    {"id": "php8.5-fpm", "label": "PHP 8.5-FPM", "optional": False, "binary": "/usr/sbin/php-fpm8.5"},
    {"id": "mailpit",    "label": "Mailpit",      "optional": True,  "binary": "/usr/local/bin/mailpit", "url": "http://localhost:8025"},
]

SYSTEMD_DIR = Path("/etc/systemd/system")

_sudo_password: str | None = None


def set_password(password: str):
    global _sudo_password
    _sudo_password = password


def validate_password(password: str) -> bool:
    result = subprocess.run(
        ["sudo", "-S", "-p", "", "true"],
        input=password + "\n",
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def _run_sudo(command: list) -> bool:
    if _sudo_password is None:
        return False
    result = subprocess.run(
        ["sudo", "-S", "-p", ""] + command,
        input=_sudo_password + "\n",
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def _sudo_write_file(dest_path: str, content: str) -> bool:
    """Escribe contenido en un archivo privilegiado usando un fichero temporal."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lamp-manager", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        return _run_sudo(["cp", tmp_path, dest_path])
    finally:
        os.unlink(tmp_path)


def get_status(service_id: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", service_id],
        capture_output=True,
        text=True
    )
    return result.stdout.strip() == "active"


def install_mailpit_service(storage_enabled: bool, storage_path: str) -> bool:
    exec_start = "/usr/local/bin/mailpit"
    if storage_enabled:
        storage_dir = str(Path(storage_path).parent)
        _run_sudo(["mkdir", "-p", storage_dir])
        exec_start += f" --database {storage_path}"

    service_content = f"""[Unit]
Description=Mailpit
After=network.target

[Service]
ExecStart={exec_start}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    if not _sudo_write_file(str(SYSTEMD_DIR / "mailpit.service"), service_content):
        return False

    _run_sudo(["systemctl", "daemon-reload"])
    _run_sudo(["systemctl", "enable", "mailpit"])
    return _run_sudo(["systemctl", "start", "mailpit"])


def uninstall_mailpit_service() -> bool:
    _run_sudo(["systemctl", "stop", "mailpit"])
    _run_sudo(["systemctl", "disable", "mailpit"])
    return _run_sudo(["rm", str(SYSTEMD_DIR / "mailpit.service")])


def start_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "start", service_id])


def stop_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "stop", service_id])


def is_installed(service: dict) -> bool:
    if DEV_MODE and service["id"] in SIMULATE_NOT_INSTALLED:
        return False
    binary = service.get("binary")
    if binary:
        return Path(binary).exists()
    result = subprocess.run(
        ["which", service["id"]],
        capture_output=True, text=True
    )
    return result.returncode == 0
