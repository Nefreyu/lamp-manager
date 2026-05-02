import re
import subprocess
from pathlib import Path
from services.systemd import _run_sudo


def get_installed_version() -> str | None:
    for ver in ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0"]:
        if Path(f"/usr/sbin/php-fpm{ver}").exists():
            return ver
    return None


def get_version() -> str | None:
    ver = get_installed_version()
    if not ver:
        return None
    result = subprocess.run([f"php{ver}", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        m = re.search(r"PHP (\d+\.\d+\.\d+)", result.stdout)
        if m:
            return m.group(1)
    return None


def list_available_extensions(ver: str) -> list[str]:
    mods_dir = Path(f"/etc/php/{ver}/mods-available")
    if not mods_dir.exists():
        return []
    return sorted(p.stem for p in mods_dir.glob("*.ini"))


def list_enabled_extensions(ver: str) -> set[str]:
    conf_dir = Path(f"/etc/php/{ver}/fpm/conf.d")
    if not conf_dir.exists():
        return set()
    result = set()
    for p in conf_dir.glob("*.ini"):
        name = re.sub(r"^\d+-", "", p.stem)
        result.add(name)
    return result


def enable_extension(ver: str, name: str) -> bool:
    if not _run_sudo(["phpenmod", "-v", ver, "-s", "fpm", name]):
        return False
    return _run_sudo(["systemctl", "reload", f"php{ver}-fpm"])


def disable_extension(ver: str, name: str) -> bool:
    if not _run_sudo(["phpdismod", "-v", ver, "-s", "fpm", name]):
        return False
    return _run_sudo(["systemctl", "reload", f"php{ver}-fpm"])
