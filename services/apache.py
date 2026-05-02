import re
import shlex
import subprocess
from pathlib import Path
from services.systemd import _run_sudo

MODS_AVAILABLE = Path("/etc/apache2/mods-available")
MODS_ENABLED = Path("/etc/apache2/mods-enabled")
APACHE_ENVVARS = "/etc/apache2/envvars"


def get_version() -> str | None:
    result = subprocess.run(["apache2", "-v"], capture_output=True, text=True)
    if result.returncode == 0:
        m = re.search(r"Apache/(\S+)", result.stdout)
        if m:
            return m.group(1)
    return None


def _run_apache_cmd(command: list) -> bool:
    bash_cmd = f". {APACHE_ENVVARS}; " + " ".join(shlex.quote(str(c)) for c in command)
    return _run_sudo(["bash", "-c", bash_cmd])


def list_available_modules() -> list[str]:
    if not MODS_AVAILABLE.exists():
        return []
    return sorted(p.stem for p in MODS_AVAILABLE.glob("*.load"))


def list_enabled_modules() -> set[str]:
    if not MODS_ENABLED.exists():
        return set()
    return {p.stem for p in MODS_ENABLED.glob("*.load")}


def enable_module(name: str) -> bool:
    if not _run_apache_cmd(["a2enmod", name]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def disable_module(name: str) -> bool:
    if not _run_apache_cmd(["a2dismod", name]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])
