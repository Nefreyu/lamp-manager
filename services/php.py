import re
import subprocess
from pathlib import Path
from services.systemd import _run_sudo, _sudo_write_file

INI_PARAMS = [
    {"key": "memory_limit",        "label": "Límite de memoria",          "hint": "Ej: 128M, 256M, 512M"},
    {"key": "upload_max_filesize", "label": "Tamaño máximo de subida",    "hint": "Ej: 2M, 10M, 50M"},
    {"key": "post_max_size",       "label": "Tamaño máximo POST",         "hint": "Debe ser mayor que upload_max_filesize"},
    {"key": "max_execution_time",  "label": "Tiempo máximo de ejecución", "hint": "En segundos. Ej: 30, 60, 120"},
    {"key": "display_errors",      "label": "Mostrar errores",            "type": "bool"},
    {"key": "date.timezone",       "label": "Zona horaria",               "hint": "Ej: Europe/Madrid"},
]


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


def get_ini_value(ver: str, key: str) -> str | None:
    path = Path(f"/etc/php/{ver}/fpm/php.ini")
    if not path.exists():
        return None
    m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", path.read_text(), re.MULTILINE)
    return m.group(1).strip() if m else None


def set_ini_values(ver: str, values: dict[str, str]) -> bool:
    path = f"/etc/php/{ver}/fpm/php.ini"
    content = Path(path).read_text()
    for key, value in values.items():
        pattern = rf"^[ \t]*;?[ \t]*{re.escape(key)}[ \t]*=[ \t]*.*$"
        replacement = f"{key} = {value}" if value else f";{key} ="
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content += f"\n{key} = {value}\n"
    if not _sudo_write_file(path, content):
        return False
    return _run_sudo(["systemctl", "reload", f"php{ver}-fpm"])


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
