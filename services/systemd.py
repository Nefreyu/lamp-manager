import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)
try:
    from config.dev import DEV_MODE, SIMULATE_NOT_INSTALLED
except ImportError:
    DEV_MODE = False
    SIMULATE_NOT_INSTALLED = []

_PHP_VERSIONS = ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0"]


def _detect_php_entry() -> dict:
    for ver in _PHP_VERSIONS:
        binary = f"/usr/sbin/php-fpm{ver}"
        if Path(binary).exists():
            return {"id": f"php{ver}-fpm", "label": "PHP-FPM", "optional": False, "binary": binary}
    # PHP no encontrado: usar la versión más reciente como placeholder para mostrar "no instalado"
    return {"id": f"php{_PHP_VERSIONS[0]}-fpm", "label": "PHP-FPM", "optional": False, "binary": f"/usr/sbin/php-fpm{_PHP_VERSIONS[0]}"}


_PHP_ENTRY = _detect_php_entry()

SERVICES = [
    {"id": "apache2",    "label": "Apache",    "optional": False, "binary": "/usr/sbin/apache2",             "url": "http://localhost", "reloadable": True, "process": "apache2"},
    {"id": "mysql",      "label": "MySQL",     "optional": False, "binary": "/usr/sbin/mysqld",                                                               "restartable": True, "process": "mysqld"},
    _PHP_ENTRY,
    {"id": "phpmyadmin", "label": "phpMyAdmin","optional": False, "binary": "/usr/share/phpmyadmin/index.php","url": "http://localhost/phpmyadmin", "web_only": True},
    {"id": "mailpit",    "label": "Mailpit",   "optional": True,  "binary": "/usr/local/bin/mailpit",         "url": "http://localhost:8025",                 "process": "mailpit"},
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


def _run_sudo_feed(command: list, data: str) -> bool:
    """Ejecuta `command` con `data` como stdin usando ficheros temporales para evitar
    problemas de buffering de sudo al leer la contraseña desde el pipe."""
    if _sudo_password is None:
        return False
    data_file = script_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lamp-manager.sql", delete=False) as f:
            f.write(data)
            data_file = f.name
        cmd_str = " ".join(shlex.quote(c) for c in command)
        script = f"#!/bin/sh\n{cmd_str} < {shlex.quote(data_file)}\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lamp-manager.sh", delete=False) as sf:
            sf.write(script)
            script_file = sf.name
        os.chmod(script_file, 0o755)
        result = subprocess.run(
            ["sudo", "-S", "-p", "", script_file],
            input=_sudo_password + "\n",
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    finally:
        for path in (data_file, script_file):
            if path:
                try:
                    os.unlink(path)
                except Exception as e:
                    log.warning("No se pudo eliminar el archivo temporal %s: %s", path, e)


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


def install_mailpit_service(storage_enabled: bool, storage_path: str, smtp_port: int = 1025, max_messages: int = 500, start: bool = True) -> bool:
    exec_start = "/usr/local/bin/mailpit"
    if storage_enabled:
        storage_dir = str(Path(storage_path).parent)
        _run_sudo(["mkdir", "-p", storage_dir])
        exec_start += f" --database {storage_path}"
    if smtp_port != 1025:
        exec_start += f" --smtp 0.0.0.0:{smtp_port}"
    if max_messages != 500:
        exec_start += f" --max {max_messages}"

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
    if start:
        return _run_sudo(["systemctl", "restart", "mailpit"])
    return True


def uninstall_mailpit_service() -> bool:
    _run_sudo(["systemctl", "stop", "mailpit"])
    _run_sudo(["systemctl", "disable", "mailpit"])
    return _run_sudo(["rm", str(SYSTEMD_DIR / "mailpit.service")])


def reload_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "reload", service_id])


def restart_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "restart", service_id])


def start_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "start", service_id])


def stop_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "stop", service_id])


def is_installed(service: dict) -> bool:
    if DEV_MODE and service["id"] in SIMULATE_NOT_INSTALLED:
        return False
    if service.get("optional"):
        return (SYSTEMD_DIR / f"{service['id']}.service").exists()
    binary = service.get("binary")
    if binary:
        return Path(binary).exists()
    return shutil.which(service["id"]) is not None


def _run_sudo_output(command: list) -> str | None:
    if _sudo_password is None:
        return None
    result = subprocess.run(
        ["sudo", "-S", "-p", ""] + command,
        input=_sudo_password + "\n",
        capture_output=True,
        text=True
    )
    return result.stdout if result.returncode == 0 else None


def get_service_ports(process: str) -> list[int]:
    output = _run_sudo_output(["ss", "-tlnp"])
    if not output:
        return []
    ports = set()
    for line in output.splitlines():
        if process not in line:
            continue
        parts = line.split()
        if len(parts) >= 4:
            addr = parts[3]
            port_str = addr.rsplit(":", 1)[-1]
            if port_str.isdigit():
                ports.add(int(port_str))
    return sorted(ports)


def clear_log(path: str) -> bool:
    return _run_sudo(["truncate", "-s", "0", path])


def read_log_tail(path: str, lines: int = 200) -> str | None:
    if not Path(path).exists():
        return None
    result = subprocess.run(
        ["tail", "-n", str(lines), path],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout
    return _run_sudo_output(["tail", "-n", str(lines), path])
