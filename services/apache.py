import re
import shlex
import subprocess
from pathlib import Path
import services.systemd as _systemd
from services.systemd import _run_sudo

MODS_AVAILABLE = Path("/etc/apache2/mods-available")
MODS_ENABLED = Path("/etc/apache2/mods-enabled")
APACHE_ENVVARS = "/etc/apache2/envvars"


def get_version() -> str | None:
    try:
        result = subprocess.run(["apache2", "-v"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode == 0:
        m = re.search(r"Apache/(\S+)", result.stdout)
        if m:
            return m.group(1)
    return None


def _run_apache_cmd(command: list) -> bool:
    bash_cmd = f". {APACHE_ENVVARS}; " + " ".join(shlex.quote(str(c)) for c in command)
    return _run_sudo(["bash", "-c", bash_cmd])


APACHE_CONF = Path("/etc/apache2/apache2.conf")


def has_server_name() -> bool:
    if not APACHE_CONF.exists():
        return True
    return any(
        line.strip().lower().startswith("servername")
        for line in APACHE_CONF.read_text().splitlines()
    )


def add_server_name() -> bool:
    ok = _run_sudo(["bash", "-c", "echo 'ServerName localhost' >> /etc/apache2/apache2.conf"])
    if ok:
        _run_sudo(["systemctl", "reload", "apache2"])
    return ok


def configtest() -> tuple[bool, str]:
    if _systemd._sudo_password is None:
        return False, "No hay contraseña configurada"
    result = subprocess.run(
        ["sudo", "-S", "-p", "", "apache2ctl", "configtest"],
        input=_systemd._sudo_password + "\n",
        capture_output=True, text=True,
    )
    output = (result.stderr or result.stdout).strip()
    return result.returncode == 0, output


def list_available_modules() -> list[str]:
    if not MODS_AVAILABLE.exists():
        return []
    return sorted(p.stem for p in MODS_AVAILABLE.glob("*.load"))


def list_enabled_modules() -> set[str]:
    if not MODS_ENABLED.exists():
        return set()
    return {p.stem for p in MODS_ENABLED.glob("*.load")}


def enable_module(name: str) -> tuple[bool, str]:
    if not _run_apache_cmd(["a2enmod", name]):
        return False, f"Error al activar el módulo {name}"
    ok, msg = configtest()
    if not ok:
        _run_apache_cmd(["a2dismod", name])
        return False, msg
    _run_sudo(["systemctl", "reload", "apache2"])
    return True, ""


def disable_module(name: str) -> tuple[bool, str]:
    if not _run_apache_cmd(["a2dismod", name]):
        return False, f"Error al desactivar el módulo {name}"
    ok, msg = configtest()
    if not ok:
        _run_apache_cmd(["a2enmod", name])
        return False, msg
    _run_sudo(["systemctl", "reload", "apache2"])
    return True, ""
