import getpass
import io
import json
import logging
import os
import re
import shlex
import subprocess
import urllib.request
import zipfile
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from services.systemd import _run_sudo, _sudo_write_file, _run_sudo_output, _run_sudo_feed, get_status
import services.nginx as nginx
import services.apache as apache
import services.hosts as hosts

log = logging.getLogger(__name__)

_FRAMEWORKS_FILE = Path.home() / ".config" / "lamp-manager" / "frameworks.json"

_DEFAULT_FRAMEWORKS = [
    {
        "id": "php",
        "label": "PHP básico",
        "description": "Sitio PHP sin framework",
    },
    {
        "id": "laravel",
        "label": "Laravel",
        "description": "composer create-project laravel/laravel",
        "requires": "composer",
        "command": "composer create-project laravel/laravel {name}",
    },
    {
        "id": "symfony",
        "label": "Symfony",
        "description": "composer create-project symfony/skeleton",
        "requires": "composer",
        "command": "composer create-project symfony/skeleton {name}",
    },
    {
        "id": "wordpress",
        "label": "WordPress",
        "description": "Descarga WordPress desde wordpress.org",
        "zip_url": "https://wordpress.org/latest.zip",
        "zip_strip_prefix": "wordpress/",
    },
]


def load_frameworks() -> list[dict]:
    if _FRAMEWORKS_FILE.exists():
        try:
            return json.loads(_FRAMEWORKS_FILE.read_text())
        except Exception as e:
            log.warning("No se pudo leer frameworks.json: %s", e)
    else:
        try:
            _FRAMEWORKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _FRAMEWORKS_FILE.write_text(
                json.dumps(_DEFAULT_FRAMEWORKS, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            log.warning("No se pudo crear frameworks.json: %s", e)
    return _DEFAULT_FRAMEWORKS


FRAMEWORKS = load_frameworks()


def is_command_installed(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def scaffold_project(framework: dict, name: str, projects_dir: str, on_progress=None) -> tuple[bool, str | None]:
    def progress(msg):
        if on_progress:
            on_progress(msg)
    try:
        base = Path(projects_dir) / name
        command = framework.get("command")
        zip_url = framework.get("zip_url")
        zip_strip_prefix = framework.get("zip_strip_prefix", "")

        if command:
            cmd_str = command.replace("{name}", name).replace("{projects_dir}", projects_dir)
            progress(f"Ejecutando: {cmd_str}…")
            result = subprocess.run(
                shlex.split(cmd_str), cwd=projects_dir, capture_output=True, text=True
            )
            if result.returncode != 0:
                return False, result.stderr or f"Error al ejecutar: {cmd_str}"
        elif zip_url:
            progress(f"Descargando {zip_url}…")
            with urllib.request.urlopen(zip_url) as response:
                data = response.read()
            progress("Extrayendo archivos…")
            base.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for member in z.namelist():
                    if zip_strip_prefix and not member.startswith(zip_strip_prefix):
                        continue
                    rel = member[len(zip_strip_prefix):]
                    if not rel:
                        continue
                    target = base / rel
                    if member.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())
        else:
            base.mkdir(parents=True, exist_ok=True)
            # Sin índice, Apache responde 403 al abrir un proyecto recién creado
            _write_initial_index(base)
        return True, None
    except Exception as e:
        log.error("Error al crear el proyecto '%s': %s", name, e)
        return False, str(e)


# La plantilla obtiene el dominio y el nombre de la base de datos de HTTP_HOST,
# así que se copia sin sustituir nada
INDEX_BASIC_TEMPLATE = Path(__file__).parent / "templates" / "index_basic.php"


def _write_initial_index(project_dir: Path) -> None:
    if any((project_dir / index).exists() for index in ("index.php", "index.html")):
        return
    (project_dir / "index.php").write_text(INDEX_BASIC_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")


HOSTS_FILE = Path("/etc/hosts")
APACHE_SITES_AVAILABLE = Path("/etc/apache2/sites-available")
APACHE_SITES_ENABLED = Path("/etc/apache2/sites-enabled")
INDEX_PAGE = Path("/var/www/html/index.html")
INDEX_BACKUP = Path("/var/www/html/index.html.lamp-manager.bak")
CERTS_DIR = Path.home() / ".local/share/lamp-manager/certs"
TRASH_DIR = Path.home() / ".local/share/lamp-manager/trash"


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    s = s[:63].rstrip('-')
    return s


# Etiqueta DNS: letras, números y guiones, sin guion al principio ni al final.
# Se admiten mayúsculas porque hay vhosts creados así antes de existir slugify.
_VHOST_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def is_valid_vhost_name(name: str) -> bool:
    return bool(_VHOST_NAME_RE.match(name))


def find_vhost_conflict(name: str, exclude: str | None = None) -> str | None:
    """Vhost existente cuyo nombre coincide con `name` sin distinguir mayúsculas.

    Los dominios no distinguen mayúsculas: demo.test y Demo.test son el mismo,
    así que dos vhosts así se pisarían en Apache, Nginx y /etc/hosts.
    """
    target = name.lower()
    return next((p for p in list_projects() if p.lower() == target and p != exclude), None)


def find_folder_conflict(parent: Path, name: str, exclude: str | None = None) -> Path | None:
    """Carpeta de `parent` cuyo nombre coincide con `name` sin distinguir mayúsculas."""
    if not parent.is_dir():
        return None
    target = name.lower()
    return next((d for d in parent.iterdir() if d.name.lower() == target and d.name != exclude), None)


def register_orphan(projects_dir: str, folder: str) -> tuple[bool, str, str]:
    """Registra una carpeta sin vhost; si su nombre no es válido la renombra antes al slug.

    Devuelve (ok, nombre del vhost, mensaje de error).
    """
    name = folder if is_valid_vhost_name(folder) else slugify(folder)
    if not name:
        return False, "", f"No se puede obtener un nombre válido a partir de «{folder}»"
    existing = find_vhost_conflict(name)
    if existing:
        return False, name, f"Ya existe un vhost llamado {existing}"
    if name != folder:
        base = Path(projects_dir)
        target = base / name
        conflict = find_folder_conflict(base, name, exclude=folder)
        if conflict:
            return False, name, f"Ya existe la carpeta {conflict}"
        try:
            (base / folder).rename(target)
        except OSError as e:
            log.error("No se pudo renombrar %s a %s: %s", folder, name, e)
            return False, name, f"No se pudo renombrar la carpeta: {e}"
        log.info("Carpeta %s renombrada a %s para registrarla", folder, name)
    if not create_vhost(name, projects_dir):
        return False, name, f"Error al registrar {name}.test"
    return True, name, ""


def list_orphan_folders(projects_dir: str) -> list[str]:
    base = Path(projects_dir)
    if not base.exists():
        return []
    projects = list_projects()
    # Una carpeta está en uso si coincide con el nombre de un vhost o si es la
    # carpeta real de su DocumentRoot (p. ej. tras renombrar el proyecto)
    used = set(projects)
    for name in projects:
        project_dir = get_project_dir(name)
        if project_dir and project_dir.parent == base:
            used.add(project_dir.name)
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and d.name not in used and not d.name.startswith(".")
    )


def list_projects() -> list[str]:
    if not APACHE_SITES_AVAILABLE.exists():
        return []
    return sorted(
        p.name.removesuffix(".test.conf")
        for p in APACHE_SITES_AVAILABLE.iterdir()
        if p.name.endswith(".test.conf")
    )


def vhost_config_path(name: str) -> Path:
    return APACHE_SITES_AVAILABLE / f"{name}.test.conf"


def vhost_is_enabled(name: str) -> bool:
    return (APACHE_SITES_ENABLED / f"{name}.test.conf").exists()


def is_mkcert_installed() -> bool:
    result = subprocess.run(["which", "mkcert"], capture_output=True, text=True)
    return result.returncode == 0


def vhost_has_https(name: str) -> bool:
    return (CERTS_DIR / f"{name}.test.pem").exists()


VHOST_ERROR_LOG = "/var/log/apache2/{name}.test-error.log"
VHOST_ACCESS_LOG = "/var/log/apache2/{name}.test-access.log"


def _vhost_config(name: str, docroot: str, https: bool = False) -> str:
    directory_block = f"""    <Directory {docroot}>
        AllowOverride All
        Require all granted
    </Directory>"""
    error_log = VHOST_ERROR_LOG.format(name=name)
    access_log = VHOST_ACCESS_LOG.format(name=name)
    http_port = apache.get_http_port()
    https_port = apache.get_https_port()

    if https:
        return f"""<VirtualHost *:{http_port}>
    ServerName {name}.test
    Redirect permanent / https://{name}.test:{https_port}/
</VirtualHost>

<VirtualHost *:{https_port}>
    ServerName {name}.test
    DocumentRoot {docroot}
    ErrorLog {error_log}
    CustomLog {access_log} combined
    SSLEngine on
    SSLCertificateFile {CERTS_DIR}/{name}.test.pem
    SSLCertificateKeyFile {CERTS_DIR}/{name}.test-key.pem
{directory_block}
</VirtualHost>
"""
    return f"""<VirtualHost *:{http_port}>
    ServerName {name}.test
    DocumentRoot {docroot}
    ErrorLog {error_log}
    CustomLog {access_log} combined
{directory_block}
</VirtualHost>
"""


def ensure_vhost_logs(name: str) -> bool:
    config = vhost_config_path(name)
    if not config.exists():
        return False
    content = _run_sudo_output(["cat", str(config)]) or ""
    if "ErrorLog" in content or "CustomLog" in content:
        return True
    error_log = VHOST_ERROR_LOG.format(name=name)
    access_log = VHOST_ACCESS_LOG.format(name=name)
    log_lines = f"    ErrorLog {error_log}\n    CustomLog {access_log} combined\n"
    last_idx = content.rfind("</VirtualHost>")
    if last_idx == -1:
        return False
    new_content = content[:last_idx] + log_lines + content[last_idx:]
    if not _sudo_write_file(str(config), new_content):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def get_vhost_log_paths(name: str) -> tuple[str, str]:
    default_error = VHOST_ERROR_LOG.format(name=name)
    default_access = VHOST_ACCESS_LOG.format(name=name)
    content = _run_sudo_output(["cat", str(vhost_config_path(name))]) or ""
    error_log = default_error
    access_log = default_access
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("ErrorLog "):
            error_log = stripped[len("ErrorLog "):].strip()
        elif stripped.startswith("CustomLog "):
            parts = stripped[len("CustomLog "):].strip().split()
            if parts:
                access_log = parts[0]
    return error_log, access_log


def _ensure_localhost_ssl():
    conf = APACHE_SITES_AVAILABLE / "000-localhost-ssl.conf"
    content = f"""<VirtualHost *:{apache.get_https_port()}>
    ServerName localhost
    DocumentRoot /var/www/html
    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/ssl-cert-snakeoil.pem
    SSLCertificateKeyFile /etc/ssl/private/ssl-cert-snakeoil.key
</VirtualHost>
"""
    _sudo_write_file(str(conf), content)
    _run_sudo(["a2ensite", "000-localhost-ssl"])


def enable_https(name: str) -> bool:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mkcert", "-install"], capture_output=True, text=True)
    result = subprocess.run(
        ["mkcert",
         "-cert-file", str(CERTS_DIR / f"{name}.test.pem"),
         "-key-file", str(CERTS_DIR / f"{name}.test-key.pem"),
         f"{name}.test"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False
    _run_sudo(["a2enmod", "ssl"])
    _ensure_localhost_ssl()
    docroot = get_docroot(name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https=True)):
        return False
    ok = _run_sudo(["systemctl", "reload", "apache2"])
    nginx.write_vhost_config(name, docroot, https=True)
    nginx.reload()
    generate_index_page()
    return ok


def disable_https(name: str) -> bool:
    (CERTS_DIR / f"{name}.test.pem").unlink(missing_ok=True)
    (CERTS_DIR / f"{name}.test-key.pem").unlink(missing_ok=True)
    docroot = get_docroot(name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https=False)):
        return False
    ok = _run_sudo(["systemctl", "reload", "apache2"])
    nginx.write_vhost_config(name, docroot, https=False)
    nginx.reload()
    generate_index_page()
    return ok


def add_hosts_entry(domain: str) -> bool:
    current = HOSTS_FILE.read_text()
    new_content = hosts.add_entry(current, domain)
    if new_content == current:
        return True
    return _sudo_write_file(str(HOSTS_FILE), new_content)


def remove_hosts_entry(domain: str) -> bool:
    current = HOSTS_FILE.read_text()
    new_content = hosts.remove_entry(current, domain)
    if new_content == current:
        return True
    return _sudo_write_file(str(HOSTS_FILE), new_content)


def generate_index_page() -> bool:
    projects = [name for name in list_projects() if vhost_is_enabled(name)]

    if not projects:
        if INDEX_BACKUP.exists():
            _run_sudo(["cp", str(INDEX_BACKUP), str(INDEX_PAGE)])
            _run_sudo(["rm", "-f", str(INDEX_BACKUP)])
        return True

    if INDEX_PAGE.exists() and not INDEX_BACKUP.exists():
        _run_sudo(["cp", str(INDEX_PAGE), str(INDEX_BACKUP)])

    _FW_LABELS = {
        "laravel":   ("Laravel",   "fw-laravel"),
        "symfony":   ("Symfony",   "fw-symfony"),
        "wordpress": ("WordPress", "fw-wordpress"),
        "php":       ("PHP",       "fw-php"),
    }

    _FW_COLORS = {
        "laravel":   {"accent": "#f87171", "rgb": "248,113,113", "band1": "#ef4444", "band2": "#b91c1c"},
        "symfony":   {"accent": "#2dd4bf", "rgb": "45,212,191",  "band1": "#14b8a6", "band2": "#0f766e"},
        "wordpress": {"accent": "#60a5fa", "rgb": "96,165,250",  "band1": "#3b82f6", "band2": "#1d4ed8"},
        "php":       {"accent": "#a78bfa", "rgb": "167,139,250", "band1": "#8b5cf6", "band2": "#6d28d9"},
    }

    _FW_LOGO_PATHS = {
        "laravel":   '<path d="M23.642 5.43a.364.364 0 01.014.1v5.149c0 .135-.073.26-.189.326l-4.323 2.49v4.934a.378.378 0 01-.188.326L9.93 23.949a.316.316 0 01-.066.027c-.008.002-.016.008-.024.01a.348.348 0 01-.192 0c-.011-.002-.02-.008-.03-.012-.02-.008-.042-.014-.062-.025L.533 18.755a.376.376 0 01-.189-.326V2.974c0-.033.005-.066.014-.098.003-.012.01-.02.014-.032a.369.369 0 01.023-.058c.004-.013.015-.022.023-.033l.033-.045c.012-.01.025-.018.037-.027.014-.012.027-.024.041-.034H.53L5.043.05a.375.375 0 01.375 0L9.93 2.647h.002c.015.01.027.021.04.033l.038.027c.013.014.02.03.033.045.008.011.02.021.025.033.01.02.017.038.024.058.003.011.01.021.013.032.01.031.014.064.014.098v9.652l3.76-2.164V5.527c0-.033.004-.066.013-.098.003-.01.01-.02.013-.032a.487.487 0 01.024-.059c.007-.012.018-.02.025-.033.012-.015.021-.03.033-.043.012-.012.025-.02.037-.028.014-.01.026-.023.041-.032h.001l4.513-2.598a.375.375 0 01.375 0l4.513 2.598c.016.01.027.021.042.031.012.01.025.018.036.028.013.014.022.03.034.044.008.012.019.021.024.033.011.02.018.04.024.06.006.01.012.021.015.032zm-.74 5.032V6.179l-1.578.908-2.182 1.256v4.283zm-4.51 7.75v-4.287l-2.147 1.225-6.126 3.498v4.325zM1.093 3.624v14.588l8.273 4.761v-4.325l-4.322-2.445-.002-.003H5.04c-.014-.01-.025-.021-.04-.031-.011-.01-.024-.018-.035-.027l-.001-.002c-.013-.012-.021-.025-.031-.04-.01-.011-.021-.022-.028-.036h-.002c-.008-.014-.013-.031-.02-.047-.006-.016-.014-.027-.018-.043a.49.49 0 01-.008-.057c-.002-.014-.006-.027-.006-.041V5.789l-2.18-1.257zM5.23.81L1.47 2.974l3.76 2.164 3.758-2.164zm1.956 13.505l2.182-1.256V3.624l-1.58.91-2.182 1.255v9.435zm11.581-10.95l-3.76 2.163 3.76 2.163 3.759-2.164zm-.376 4.978L16.21 7.087 14.63 6.18v4.283l2.182 1.256 1.58.908zm-8.65 9.654l5.514-3.148 2.756-1.572-3.757-2.163-4.323 2.489-3.941 2.27z"/>',
        "symfony":   '<path d="M24 12c0 6.628-5.372 12-12 12S0 18.628 0 12 5.372 0 12 0s12 5.372 12 12zm-6.753-7.561c-1.22.042-2.283.715-3.075 1.644-.878 1.02-1.461 2.229-1.881 3.461-.753-.614-1.332-1.414-2.539-1.761-.966-.297-2.015-.105-2.813.514-.41.319-.71.757-.861 1.254-.36 1.176.381 2.225.719 2.6l.737.79c.15.154.519.56.339 1.138-.193.631-.951 1.037-1.732.799-.348-.106-.848-.366-.734-.73.045-.15.152-.263.21-.391.052-.11.077-.194.095-.242.141-.465-.053-1.07-.551-1.223-.465-.143-.939-.03-1.125.566-.209.68.117 1.913 1.86 2.449 2.04.628 3.765-.484 4.009-1.932.153-.907-.255-1.582-1.006-2.447l-.612-.677c-.371-.37-.497-1.002-.114-1.485.324-.409.785-.584 1.539-.379 1.103.3 1.594 1.063 2.412 1.68-.338 1.11-.56 2.223-.759 3.222l-.123.746c-.585 3.07-1.033 4.757-2.194 5.726-.234.166-.57.416-1.073.434-.266.005-.352-.176-.355-.257-.006-.184.15-.271.255-.353.154-.083.39-.224.372-.674-.016-.532-.456-.994-1.094-.973-.477.017-1.203.465-1.176 1.286.028.85.819 1.485 2.012 1.444.638-.021 2.062-.281 3.464-1.949 1.633-1.911 2.09-4.101 2.434-5.706l.383-2.116c.213.024.441.042.69.048 2.032.044 3.049-1.01 3.064-1.776.01-.464-.304-.921-.744-.91-.386.009-.718.278-.806.654-.094.428.646.813.068 1.189-.41.266-1.146.452-2.184.3l.188-1.042c.386-1.976.859-4.407 2.661-4.467.132-.007.612.006.623.323.003.105-.022.134-.147.375-.115.155-.174.345-.168.537.017.504.4.836.957.816.743-.023.955-.748.945-1.119-.032-.874-.952-1.424-2.17-1.386z"/>',
        "wordpress": '<path d="M21.469 6.825c.84 1.537 1.318 3.3 1.318 5.175 0 3.979-2.156 7.456-5.363 9.325l3.295-9.527c.615-1.54.82-2.771.82-3.864 0-.405-.026-.78-.07-1.11m-7.981.105c.647-.03 1.232-.105 1.232-.105.582-.075.514-.93-.067-.899 0 0-1.755.135-2.88.135-1.064 0-2.85-.15-2.85-.15-.585-.03-.661.855-.075.885 0 0 .54.061 1.125.09l1.68 4.605-2.37 7.08L5.354 6.9c.649-.03 1.234-.1 1.234-.1.585-.075.516-.93-.065-.896 0 0-1.746.138-2.874.138-.2 0-.438-.008-.69-.015C4.911 3.15 8.235 1.215 12 1.215c2.809 0 5.365 1.072 7.286 2.833-.046-.003-.091-.009-.141-.009-1.06 0-1.812.923-1.812 1.914 0 .89.513 1.643 1.06 2.531.411.72.89 1.643.89 2.977 0 .915-.354 1.994-.821 3.479l-1.075 3.585-3.9-11.61.001.014zM12 22.784c-1.059 0-2.081-.153-3.048-.437l3.237-9.406 3.315 9.087c.024.053.05.101.078.149-1.12.393-2.325.609-3.582.609M1.211 12c0-1.564.336-3.05.935-4.39L7.29 21.709C3.694 19.96 1.212 16.271 1.211 12M12 0C5.385 0 0 5.385 0 12s5.385 12 12 12 12-5.385 12-12S18.615 0 12 0"/>',
        "php":       '<path d="M7.01 10.207h-.944l-.515 2.648h.838c.556 0 .97-.105 1.242-.314.272-.21.455-.559.55-1.049.092-.47.05-.802-.124-.995-.175-.193-.523-.29-1.047-.29zM12 5.688C5.373 5.688 0 8.514 0 12s5.373 6.313 12 6.313S24 15.486 24 12c0-3.486-5.373-6.312-12-6.312zm-3.26 7.451c-.261.25-.575.438-.917.551-.336.108-.765.164-1.285.164H5.357l-.327 1.681H3.652l1.23-6.326h2.65c.797 0 1.378.209 1.744.628.366.418.476 1.002.33 1.752a2.836 2.836 0 0 1-.305.847c-.143.255-.33.49-.561.703zm4.024.715l.543-2.799c.063-.318.039-.536-.068-.651-.107-.116-.336-.174-.687-.174H11.46l-.704 3.625H9.388l1.23-6.327h1.367l-.327 1.682h1.218c.767 0 1.295.134 1.586.401s.378.7.263 1.299l-.572 2.944h-1.389zm7.597-2.265a2.782 2.782 0 0 1-.305.847c-.143.255-.33.49-.561.703a2.44 2.44 0 0 1-.917.551c-.336.108-.765.164-1.286.164h-1.18l-.327 1.682h-1.378l1.23-6.326h2.649c.797 0 1.378.209 1.744.628.366.417.477 1.001.331 1.751zM17.766 10.207h-.943l-.516 2.648h.838c.557 0 .971-.105 1.242-.314.272-.21.455-.559.551-1.049.092-.47.049-.802-.125-.995s-.524-.29-1.047-.29z"/>',
    }

    _ICON_GLOBE  = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
    _ICON_FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    _ICON_CODE   = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'

    _TOOL_ICONS = {
        "phpmyadmin": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></svg>',
        "mailpit":    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
    }

    def _tools_html():
        from services.systemd import SERVICES, is_installed, get_status
        items = []
        for svc in SERVICES:
            icon = _TOOL_ICONS.get(svc["id"])
            if icon is None or not svc.get("url") or not is_installed(svc):
                continue
            active = get_status("apache2") if svc.get("web_only") else get_status(svc["id"])
            dot_cls = "tool-dot-on" if active else "tool-dot-off"
            state = "activo" if active else "detenido"
            items.append(
                f'      <a href="{html_escape(svc["url"])}" target="_blank" class="tool" title="{state}">'
                f'{icon}<span class="tool-label">{html_escape(svc["label"])}</span>'
                f'<span class="tool-dot {dot_cls}"></span></a>'
            )
        if not items:
            return ""
        return (
            '    <section class="tools">\n'
            '      <h2 class="tools-title">Herramientas</h2>\n'
            '      <div class="tools-row">\n'
            + "\n".join(items)
            + "\n      </div>\n"
            "    </section>\n"
        )

    def _card(name, i=0):
        docroot     = get_docroot(name)
        has_https   = vhost_has_https(name)
        fw_id       = detect_framework(docroot)
        fw_label, fw_cls = _FW_LABELS[fw_id]
        c           = _FW_COLORS[fw_id]
        logo        = f'<svg class="fw-logo" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">{_FW_LOGO_PATHS[fw_id]}</svg>'
        protocol    = "https" if has_https else "http"
        domain      = f"{name}.test"
        project_dir = str(_project_dir_from_docroot(docroot)) if docroot else ""

        nginx_port       = nginx.get_https_port() if has_https else nginx.get_http_port()
        nginx_url        = f"{protocol}://{domain}:{nginx_port}"
        nginx_link = (
            f'<a href="{html_escape(nginx_url)}" target="_blank" class="card-link card-link-secondary">'
            f'Nginx :{nginx_port} <span class="arrow">&#8594;</span></a>'
            if nginx_active else ""
        )

        apache_port    = apache.get_https_port() if has_https else apache.get_http_port()
        apache_default = 443 if has_https else 80
        apache_domain  = f"{domain}:{apache_port}" if apache_port != apache_default else domain
        apache_url     = f"{protocol}://{apache_domain}"

        branch   = get_git_branch(project_dir)
        size     = get_project_size(project_dir)
        last_mod = get_project_last_modified(project_dir)
        errors   = get_recent_error_count(name)
        has_db   = database_exists(name)

        https_badge = (
            '<span class="band-badge band-badge-on">HTTPS</span>'
            if has_https else
            '<span class="band-badge">HTTP</span>'
        )
        branch_html = (
            f'<span class="branch-badge">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>'
            f'{html_escape(branch)}</span>'
            if branch else ""
        )

        stats = []
        if size:
            stats.append(f'<span class="stat">&#128230; {html_escape(size)}</span>')
        if last_mod:
            stats.append(f'<span class="stat">&#128336; {html_escape(last_mod)}</span>')
        if errors > 0:
            label = "error" if errors == 1 else "errores"
            stats.append(f'<span class="stat stat-error">&#9888; {errors} {label}</span>')
        if has_db:
            stats.append('<span class="stat stat-db">&#128451; Base de datos</span>')

        stats_row = (
            f'<div class="card-stats">{"".join(stats)}</div>'
            if stats else ""
        )

        return f"""      <div class="card" style="--fw:{c['accent']}; --fw-glow:rgba({c['rgb']},0.30); --band1:{c['band1']}; --band2:{c['band2']}; animation-delay:{i * 50}ms">
        <div class="card-band">
          {logo}
          <span class="card-name">{html_escape(name)}</span>
          {https_badge}
        </div>
        <div class="card-body">
          <div class="card-info">
            <div class="info-row">{_ICON_GLOBE}<span class="value">{html_escape(domain)}</span></div>
            <div class="info-row">{_ICON_CODE}<span class="fw-badge {fw_cls}">{fw_label}</span>{branch_html}</div>
            <div class="info-row">{_ICON_FOLDER}<span class="value docroot">{html_escape(docroot)}</span></div>
          </div>
          {stats_row}
          <a href="{html_escape(apache_url)}" target="_blank" class="card-link">Abrir proyecto <span class="arrow">&#8594;</span></a>
          {nginx_link}
        </div>
      </div>"""

    nginx_active = get_status("nginx")
    cards = "\n".join(_card(p, i) for i, p in enumerate(projects))
    tools_section = _tools_html()
    count = len(projects)
    plural = "proyecto activo" if count == 1 else "proyectos activos"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LAMP Manager</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:           #0f172a;
      --surface:      #1e293b;
      --border:       #334155;
      --text:         #f1f5f9;
      --text-muted:   #94a3b8;
      --accent:       #3b82f6;
      --accent-hover: #2563eb;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Cantarell, sans-serif;
      background:
        radial-gradient(1100px 520px at 50% -8%, #1b2742 0%, rgba(27,39,66,0) 60%),
        var(--bg);
      background-attachment: fixed;
      color: var(--text);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      position: relative;
      background: linear-gradient(135deg, #1f2b44 0%, #131c30 100%);
      border-bottom: 1px solid var(--border);
      padding: 20px 32px;
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    header::after {{
      content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px;
      background: linear-gradient(90deg, var(--accent), #6366f1 35%, transparent 80%);
    }}
    .logo {{
      width: 40px; height: 40px; border-radius: 11px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      background: linear-gradient(135deg, #3b82f6, #6366f1);
      box-shadow: 0 6px 16px -5px rgba(59,130,246,0.65);
    }}
    .logo svg {{ color: #fff; }}
    .brand-text {{ display: flex; flex-direction: column; gap: 1px; }}
    header h1 {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
    .brand-sub {{ font-size: 0.74rem; color: var(--text-muted); }}
    .header-count {{
      margin-left: auto; font-size: 0.8rem; color: var(--text-muted);
      padding: 6px 14px; border: 1px solid var(--border); border-radius: 20px;
      background: rgba(148,163,184,0.06);
    }}
    main {{ padding: 32px; max-width: 1500px; margin: 0 auto; }}
    @keyframes cardIn {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to   {{ opacity: 1; transform: none; }}
    }}
    .tools {{ margin-bottom: 32px; }}
    .tools-title {{
      font-size: 0.78rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted); margin-bottom: 12px;
    }}
    .tools-row {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .tool {{
      display: inline-flex; align-items: center; gap: 9px;
      padding: 10px 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      color: var(--text); text-decoration: none;
      font-size: 0.875rem; font-weight: 500;
      transition: border-color 0.2s, transform 0.15s;
    }}
    .tool:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
    .tool svg {{ color: var(--text-muted); flex-shrink: 0; }}
    .tool:hover svg {{ color: var(--accent); }}
    .tool-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
    .tool-dot-on  {{ background: #4ade80; box-shadow: 0 0 0 3px rgba(74,222,128,0.15); }}
    .tool-dot-off {{ background: #64748b; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
      gap: 20px;
    }}
    .card {{
      position: relative;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: cardIn 0.45s ease both;
      transition: border-color 0.2s, transform 0.18s, box-shadow 0.25s;
    }}
    .card:hover {{
      transform: translateY(-3px);
      border-color: var(--fw, var(--accent));
      box-shadow: 0 16px 34px -16px var(--fw-glow, rgba(59,130,246,0.3));
    }}
    .card-band {{
      display: flex; align-items: center; gap: 10px;
      padding: 14px 18px;
      background: linear-gradient(135deg, var(--band1), var(--band2));
      color: #fff;
    }}
    .card-band .fw-logo {{ flex-shrink: 0; opacity: 0.95; filter: drop-shadow(0 1px 1px rgba(0,0,0,0.25)); }}
    .card-name {{ font-size: 1.05rem; font-weight: 700; letter-spacing: -0.01em; color: #fff; }}
    .band-badge {{
      margin-left: auto; flex-shrink: 0;
      font-size: 0.66rem; font-weight: 700;
      padding: 3px 9px; border-radius: 20px;
      text-transform: uppercase; letter-spacing: 0.05em;
      background: rgba(255,255,255,0.18); color: #fff;
      border: 1px solid rgba(255,255,255,0.35);
    }}
    .band-badge-on {{ background: rgba(255,255,255,0.92); color: #0f172a; border-color: transparent; }}
    .card-body {{
      display: flex; flex-direction: column; gap: 14px;
      padding: 18px;
    }}
    .card-info {{ display: flex; flex-direction: column; gap: 9px; }}
    .info-row {{ display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--text-muted); }}
    .info-row svg {{ flex-shrink: 0; }}
    .value {{ color: var(--text); word-break: break-all; }}
    .docroot {{ font-size: 0.78rem; color: var(--text-muted); }}
    .fw-badge {{
      font-size: 0.72rem; font-weight: 600;
      padding: 2px 9px; border-radius: 4px;
      text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .fw-laravel   {{ background: rgba(255,75,75,0.15);   color: #f87171; border: 1px solid rgba(255,75,75,0.3); }}
    .fw-symfony   {{ background: rgba(0,210,180,0.12);   color: #2dd4bf; border: 1px solid rgba(0,210,180,0.3); }}
    .fw-wordpress {{ background: rgba(96,165,250,0.12);  color: #60a5fa; border: 1px solid rgba(96,165,250,0.3); }}
    .fw-php       {{ background: rgba(167,139,250,0.12); color: #a78bfa; border: 1px solid rgba(167,139,250,0.3); }}
    .branch-badge {{
      display: inline-flex; align-items: center; gap: 4px;
      margin-left: 8px;
      font-size: 0.78rem; color: #4ade80;
    }}
    .card-stats {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .stat {{
      font-size: 0.75rem; padding: 3px 8px; border-radius: 4px;
      background: rgba(148,163,184,0.08); color: var(--text-muted);
      border: 1px solid rgba(148,163,184,0.15);
    }}
    .stat-error {{ background: rgba(239,68,68,0.12); color: #f87171; border-color: rgba(239,68,68,0.25); }}
    .stat-db    {{ background: rgba(59,130,246,0.12); color: #60a5fa; border-color: rgba(59,130,246,0.25); }}
    .card-link {{
      display: flex; align-items: center; justify-content: center; gap: 7px;
      padding: 10px 16px;
      background: linear-gradient(135deg, var(--accent), var(--accent-hover));
      color: white;
      text-decoration: none; border-radius: 9px;
      font-size: 0.875rem; font-weight: 600;
      box-shadow: 0 6px 16px -8px rgba(59,130,246,0.7);
      transition: filter 0.15s, box-shadow 0.2s;
      margin-top: auto;
    }}
    .card-link:hover {{ filter: brightness(1.08); box-shadow: 0 8px 20px -8px rgba(59,130,246,0.85); }}
    .card-link .arrow {{ transition: transform 0.18s; }}
    .card-link:hover .arrow {{ transform: translateX(4px); }}
    .card-link-secondary {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      box-shadow: none;
    }}
    .card-link-secondary:hover {{ filter: none; border-color: var(--accent); color: var(--text); box-shadow: none; }}
    footer {{
      text-align: center; padding: 28px;
      color: var(--text-muted); font-size: 0.78rem;
      border-top: 1px solid var(--border);
      margin-top: 20px;
    }}
  </style>
</head>
<body>
  <header>
    <span class="logo"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg></span>
    <div class="brand-text">
      <h1>LAMP Manager</h1>
      <span class="brand-sub">Entorno de desarrollo local</span>
    </div>
    <span class="header-count">{count} {plural}</span>
  </header>
  <main>
{tools_section}    <div class="grid">
{cards}
    </div>
  </main>
  <footer>LAMP Manager &middot; entorno local</footer>
</body>
</html>
"""
    return _sudo_write_file(str(INDEX_PAGE), html)


def _relative_time(timestamp: float) -> str:
    delta = datetime.now() - datetime.fromtimestamp(timestamp)
    s = delta.total_seconds()
    if s < 120:
        return "hace un momento"
    if s < 3600:
        return f"hace {int(s / 60)}m"
    if s < 86400:
        return f"hace {int(s / 3600)}h"
    if s < 604800:
        return f"hace {int(s / 86400)}d"
    return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y")


def get_git_branch(project_dir: str) -> str | None:
    if not project_dir or not Path(project_dir).exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3
        )
        branch = r.stdout.strip()
        return branch if r.returncode == 0 and branch and branch != "HEAD" else None
    except Exception:
        return None


def get_project_last_modified(project_dir: str) -> str | None:
    if not project_dir or not Path(project_dir).exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", project_dir, "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            return _relative_time(float(r.stdout.strip()))
        return _relative_time(Path(project_dir).stat().st_mtime)
    except Exception:
        return None


def get_project_size(project_dir: str) -> str | None:
    if not project_dir or not Path(project_dir).exists():
        return None
    try:
        r = subprocess.run(
            ["du", "-sh", "--exclude=.git", "--exclude=vendor", "--exclude=node_modules", project_dir],
            capture_output=True, text=True, timeout=10
        )
        return r.stdout.split()[0] if r.returncode == 0 else None
    except Exception:
        return None


def get_recent_error_count(name: str) -> int:
    error_log = VHOST_ERROR_LOG.format(name=name)
    try:
        content = _run_sudo_output(["tail", "-n", "500", error_log]) or ""
        return sum(1 for line in content.splitlines() if "[error]" in line.lower())
    except Exception:
        return 0


def detect_framework(docroot: str) -> str:
    base = Path(docroot)
    parent = base.parent
    for d in (base, parent):
        if (d / "artisan").exists():
            return "laravel"
        if (d / "symfony.lock").exists() or (d / "bin" / "console").exists():
            return "symfony"
        if (d / "wp-config.php").exists() or (d / "wp-config-sample.php").exists():
            return "wordpress"
    return "php"


def _read_root_file(path: Path) -> str | None:
    """Lee un fichero de root; recurre a sudo para los creados en 0600 por versiones anteriores."""
    try:
        return path.read_text()
    except PermissionError:
        return _run_sudo_output(["cat", str(path)])
    except OSError as e:
        log.warning("No se pudo leer %s: %s", path, e)
        return None


def repair_config_permissions() -> bool:
    """Deja en 0644 los ficheros que versiones anteriores escribieron en 0600."""
    candidates = [
        *APACHE_SITES_AVAILABLE.glob("*.test.conf"),
        APACHE_SITES_AVAILABLE / "000-localhost-ssl.conf",
        *nginx.SITES_AVAILABLE.glob("*.test.conf"),
        nginx.SITES_AVAILABLE / f"{nginx.DEFAULT_SITE_NAME}.conf",
        Path("/etc/systemd/system/mailpit.service"),
    ]
    unreadable = [str(p) for p in candidates if p.exists() and not os.access(p, os.R_OK)]
    if not unreadable:
        return True
    log.info("Corrigiendo permisos de %d ficheros de configuración", len(unreadable))
    return _run_sudo(["chmod", "0644", *unreadable])


def get_docroot(name: str) -> str:
    config = vhost_config_path(name)
    if not config.exists():
        return ""
    content = _read_root_file(config)
    if not content:
        return ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("DocumentRoot "):
            return stripped[len("DocumentRoot "):].strip()
    return ""


def _apply_apache_config(path: Path, new_content: str) -> tuple[bool, str]:
    """Escribe una config de Apache, la valida con configtest y recarga.

    Si la validación falla se restaura el contenido anterior: una config rota no
    impide el reload en caliente, pero sí que Apache arranque tras reiniciar.
    """
    previous = _read_root_file(path) if path.exists() else None
    if path.exists() and previous is None:
        return False, f"No se pudo leer la configuración actual de {path}"
    if not _sudo_write_file(str(path), new_content):
        return False, f"No se pudo escribir {path}"
    ok, output = apache.configtest()
    if not ok:
        log.warning("configtest falló tras escribir %s: %s", path, output)
        if previous is not None:
            _sudo_write_file(str(path), previous)
        else:
            _run_sudo(["rm", "-f", str(path)])
        return False, output or "La configuración de Apache no es válida"
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False, "La configuración es válida, pero Apache no se pudo recargar"
    return True, ""


def docroots_in_config(content: str) -> list[str]:
    """Rutas de todas las directivas DocumentRoot de una config de Apache."""
    result = []
    for line in content.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "documentroot":
            result.append(parts[1].strip().strip("\"'"))
    return result


def docroot_location_error(docroot: str, projects_dir: str) -> str:
    """Mensaje de error si el DocumentRoot queda fuera del directorio de proyectos; "" si es válido.

    La app solo gestiona proyectos dentro de ese directorio (detección de carpetas,
    renombrado, papelera, watcher de git): fuera de él quedarían vhosts sin control.
    """
    # Se valida la carpeta del proyecto (sin /public), igual que hace la papelera
    if is_inside_projects_dir(_project_dir_from_docroot(docroot), projects_dir):
        return ""
    return f"El DocumentRoot debe estar dentro de {projects_dir} (se ha indicado {docroot})"


def list_vhosts_outside(projects_dir: str) -> list[str]:
    return [
        name for name in list_projects()
        if get_docroot(name) and not is_inside_projects_dir(get_project_dir(name), projects_dir)
    ]


def save_vhost_config(name: str, content: str, projects_dir: str) -> tuple[bool, str]:
    for docroot in docroots_in_config(content):
        error = docroot_location_error(docroot, projects_dir)
        if error:
            return False, error
    return _apply_apache_config(vhost_config_path(name), content)


def update_docroot(name: str, new_docroot: str, projects_dir: str) -> tuple[bool, str]:
    config = vhost_config_path(name)
    if not config.exists():
        return False, f"No existe la configuración de {name}.test"
    error = docroot_location_error(new_docroot, projects_dir)
    if error:
        return False, error
    # Un DocumentRoot inexistente no hace fallar a Apache, pero deja el sitio en 403
    if not Path(new_docroot).is_dir():
        log.warning("DocumentRoot inexistente para %s: %s", name, new_docroot)
        return False, f"El directorio {new_docroot} no existe"
    content = _read_root_file(config)
    if content is None:
        return False, f"No se pudo leer la configuración de {name}.test"
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        indent = " " * (len(line) - len(line.lstrip()))
        if stripped.startswith("DocumentRoot "):
            lines.append(f"{indent}DocumentRoot {new_docroot}")
        elif stripped.startswith("<Directory ") and stripped.endswith(">"):
            lines.append(f"{indent}<Directory {new_docroot}>")
        else:
            lines.append(line)
    ok, error = _apply_apache_config(config, "\n".join(lines) + "\n")
    if not ok:
        return False, error
    nginx.write_vhost_config(name, new_docroot, https=vhost_has_https(name))
    nginx.reload()
    generate_index_page()
    return True, ""


def _detect_docroot(projects_dir: str, name: str) -> str:
    base = Path(projects_dir) / name
    public = base / "public"
    return str(public) if public.is_dir() else str(base)


def create_vhost(name: str, projects_dir: str) -> bool:
    # Un nombre con espacios u otros caracteres genera un ServerName inválido
    # y Apache entero deja de arrancar
    if not is_valid_vhost_name(name):
        log.error("Nombre de vhost no válido: %r", name)
        return False
    existing = find_vhost_conflict(name, exclude=name)
    if existing:
        log.error("El vhost %s choca con el existente %s (los dominios no distinguen mayúsculas)", name, existing)
        return False
    docroot = _detect_docroot(projects_dir, name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot)):
        return False
    nginx.ensure_default_site()
    nginx.write_vhost_config(name, docroot)
    base_dir = Path(projects_dir)
    if base_dir.exists() and not os.access(base_dir, os.W_OK):
        user = getpass.getuser()
        _run_sudo(["chown", "-R", f"{user}:{user}", str(base_dir)])
    Path(docroot).mkdir(parents=True, exist_ok=True)
    project_dir = Path(projects_dir) / name
    if project_dir.exists():
        user = getpass.getuser()
        _run_sudo(["chown", "-R", f"{user}:www-data", str(project_dir)])
        _run_sudo(["chmod", "-R", "ug+rwX", str(project_dir)])
        _run_sudo(["find", str(project_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"])
    if not add_hosts_entry(f"{name}.test"):
        return False
    _run_sudo(["a2enmod", "rewrite"])
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    _run_sudo(["systemctl", "reload", "apache2"])
    nginx.enable_site(f"{name}.test.conf")
    nginx.reload()
    create_database(name)
    generate_index_page()
    return True


def create_database(name: str) -> bool:
    if not is_command_installed("mysql"):
        return False
    return _run_sudo([
        "mysql", "-e",
        f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    ])


def database_exists(name: str) -> bool:
    result = _run_sudo_output(["mysql", "--batch", "--skip-column-names", "-e", f"SHOW DATABASES LIKE '{name}'"])
    return bool(result and name in result)


def drop_database(name: str) -> bool:
    return _run_sudo(["mysql", "-e", f"DROP DATABASE IF EXISTS `{name}`"])


def enable_vhost(name: str) -> bool:
    if not add_hosts_entry(f"{name}.test"):
        return False
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    # Reescribe la config de Nginx (no solo la re-habilita): un vhost creado
    # antes de que existiera esta función nunca tuvo sites-available de Nginx,
    # y symlinkar un archivo inexistente rompe nginx -t para todos los vhosts.
    nginx.write_vhost_config(name, get_docroot(name), https=vhost_has_https(name))
    nginx.enable_site(f"{name}.test.conf")
    nginx.reload()
    generate_index_page()
    return True


def disable_vhost(name: str) -> bool:
    if not _run_sudo(["a2dissite", f"{name}.test.conf"]):
        return False
    remove_hosts_entry(f"{name}.test")
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    nginx.disable_site(f"{name}.test.conf")
    nginx.reload()
    generate_index_page()
    return True


def sync_nginx() -> bool:
    """Sincroniza la config de Nginx con el estado actual de los vhosts de Apache.

    Se ejecuta al arrancar la app para que los proyectos creados antes de que
    existiera esta función queden disponibles en Nginx sin esperar a que el
    usuario los toque.
    """
    repair_config_permissions()
    nginx.ensure_default_site()
    ok = True
    for name in list_projects():
        if not vhost_is_enabled(name):
            continue
        docroot = get_docroot(name)
        https = vhost_has_https(name)
        if not nginx.write_vhost_config(name, docroot, https=https):
            ok = False
        if not nginx.enable_site(f"{name}.test.conf"):
            ok = False
    nginx.reload()
    generate_index_page()
    return ok


def sync_apache() -> bool:
    """Regenera la config de Apache de los vhosts habilitados con los puertos
    actuales (llamar tras cambiar los puertos de Apache en Ajustes)."""
    ok = True
    if not apache.write_ports_conf():
        ok = False
    if not apache.sync_default_site_port():
        ok = False
    if (APACHE_SITES_AVAILABLE / "000-localhost-ssl.conf").exists():
        _ensure_localhost_ssl()
    for name in list_projects():
        if not vhost_is_enabled(name):
            continue
        docroot = get_docroot(name)
        https = vhost_has_https(name)
        if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https=https)):
            ok = False
    # restart (no reload): un cambio en las directivas Listen de ports.conf no
    # se aplica con un reload/graceful restart de Apache, hace falta reinicio completo.
    if not _run_sudo(["systemctl", "restart", "apache2"]):
        ok = False
    generate_index_page()
    return ok


def _project_dir_from_docroot(docroot: str) -> Path | None:
    if not docroot:
        return None
    p = Path(docroot)
    return p.parent if p.name == "public" else p


def get_project_dir(name: str) -> Path | None:
    return _project_dir_from_docroot(get_docroot(name))


def plan_project_rename(name: str, new_docroot: str, projects_dir: str) -> tuple[Path, Path] | None:
    """Si `new_docroot` solo cambia el nombre de la carpeta del proyecto, devuelve
    (carpeta actual, carpeta nueva). En cualquier otro caso devuelve None."""
    old_docroot = get_docroot(name)
    old_project = _project_dir_from_docroot(old_docroot)
    if old_project is None or not old_project.is_dir():
        return None

    new_root = Path(new_docroot)
    if Path(old_docroot).name == "public":
        if new_root.name != "public":
            return None
        new_project = new_root.parent
    else:
        new_project = new_root

    base = Path(projects_dir).resolve()
    old_resolved = old_project.resolve()
    if (
        new_project.exists()
        or new_project.parent.resolve() != old_resolved.parent
        or old_resolved.parent != base
    ):
        return None
    return old_project, new_project


def rename_project(name: str, new_docroot: str, src: Path, dst: Path, projects_dir: str) -> tuple[bool, str]:
    """Renombra la carpeta del proyecto y apunta el vhost a ella; si falla, lo deshace."""
    old_docroot = get_docroot(name)
    try:
        src.rename(dst)
    except OSError as e:
        log.error("No se pudo renombrar %s a %s: %s", src, dst, e)
        return False, f"No se pudo renombrar la carpeta: {e}"
    ok, error = update_docroot(name, new_docroot, projects_dir)
    if ok:
        return True, ""

    log.error("Falló la actualización del vhost %s; deshaciendo el renombrado", name)
    try:
        dst.rename(src)
    except OSError as e:
        log.error("No se pudo deshacer el renombrado de %s: %s", dst, e)
        return False, f"{error}\nNo se pudo devolver la carpeta a {src}: {e}"
    update_docroot(name, old_docroot, projects_dir)
    return False, error


def is_inside_projects_dir(path: Path | None, projects_dir: str) -> bool:
    """Indica si `path` está dentro del directorio de proyectos, sin ser el propio directorio."""
    if path is None:
        return False
    base = Path(projects_dir).resolve()
    target = path.resolve()
    return target != base and target.is_relative_to(base)


def trash_vhost(name: str, projects_dir: str) -> tuple[bool, str]:
    """Mueve el vhost a la papelera. Devuelve (ok, aviso para el usuario)."""
    trash_id = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    item_dir = TRASH_DIR / trash_id
    item_dir.mkdir(parents=True, exist_ok=True)

    project_dir = _project_dir_from_docroot(get_docroot(name))
    # El DocumentRoot se puede editar a mano: si apunta fuera del directorio de
    # proyectos (o al propio directorio), mover su carpeta con sudo se llevaría
    # por delante cosas que no son del proyecto
    move_files = project_dir is not None and project_dir.exists() and is_inside_projects_dir(project_dir, projects_dir)
    warning = ""
    if project_dir is not None and project_dir.exists() and not move_files:
        warning = (
            f"La carpeta {project_dir} no se ha movido a la papelera porque está "
            f"fuera del directorio de proyectos ({projects_dir})."
        )
        log.warning("trash_vhost(%s): %s", name, warning)

    meta = {
        "trash_id": trash_id,
        "name": name,
        "project_dir": str(project_dir) if project_dir else None,
        "deleted_at": datetime.now().isoformat(),
        "has_db": False,
        "files_moved": move_files,
    }

    config_content = _run_sudo_output(["cat", str(vhost_config_path(name))])
    if config_content:
        (item_dir / "vhost.conf").write_text(config_content)

    nginx_config_content = _run_sudo_output(["cat", str(nginx.vhost_config_path(name))])
    if nginx_config_content:
        (item_dir / "vhost-nginx.conf").write_text(nginx_config_content)

    _run_sudo(["a2dissite", f"{name}.test.conf"])
    remove_hosts_entry(f"{name}.test")
    _run_sudo(["systemctl", "reload", "apache2"])
    _run_sudo(["rm", "-f", str(vhost_config_path(name))])

    nginx.disable_site(f"{name}.test.conf")
    nginx.remove_vhost_config(name)
    nginx.reload()

    if database_exists(name) and is_command_installed("mysqldump"):
        dump = _run_sudo_output(["mysqldump", "--databases", name, "--default-character-set=utf8mb4"])
        if dump:
            (item_dir / "database.sql").write_text(dump)
            meta["has_db"] = True
        drop_database(name)

    cert = CERTS_DIR / f"{name}.test.pem"
    key = CERTS_DIR / f"{name}.test-key.pem"
    if cert.exists() or key.exists():
        certs_bak = item_dir / "certs"
        certs_bak.mkdir(exist_ok=True)
        for f in (cert, key):
            if f.exists():
                (certs_bak / f.name).write_bytes(f.read_bytes())
                f.unlink()

    if move_files:
        _run_sudo(["mv", str(project_dir), str(item_dir / "files")])

    logs_bak = item_dir / "logs"
    apache_logs = (VHOST_ERROR_LOG.format(name=name), VHOST_ACCESS_LOG.format(name=name))
    nginx_logs = (nginx.VHOST_ERROR_LOG.format(name=name), nginx.VHOST_ACCESS_LOG.format(name=name))
    for prefix, log_path in [("apache", p) for p in apache_logs] + [("nginx", p) for p in nginx_logs]:
        if Path(log_path).exists():
            logs_bak.mkdir(exist_ok=True)
            _run_sudo(["mv", log_path, str(logs_bak / f"{prefix}-{Path(log_path).name}")])

    (item_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    generate_index_page()
    return True, warning


def list_trash() -> list[dict]:
    if not TRASH_DIR.exists():
        return []
    items = []
    for item_dir in TRASH_DIR.iterdir():
        meta_path = item_dir / "meta.json"
        if meta_path.exists():
            try:
                items.append(json.loads(meta_path.read_text()))
            except Exception as e:
                log.warning("No se pudo leer metadatos de papelera %s: %s", meta_path, e)
    return sorted(items, key=lambda x: x.get("deleted_at", ""), reverse=True)


def restore_vhost(trash_id: str, projects_dir: str) -> tuple[bool, str]:
    """Restaura un vhost de la papelera. Devuelve (ok, mensaje de error)."""
    item_dir = TRASH_DIR / trash_id
    meta_path = item_dir / "meta.json"
    if not meta_path.exists():
        return False, "El elemento ya no está en la papelera"

    try:
        meta = json.loads(meta_path.read_text())
        name = meta["name"]
    except (OSError, ValueError, KeyError) as e:
        log.error("Metadatos de papelera inválidos en %s: %s", meta_path, e)
        return False, "Los datos de este elemento de la papelera están dañados"

    if meta.get("project_dir"):
        project_dir = Path(meta["project_dir"])
    else:
        project_dir = Path(projects_dir) / name

    files_dir = item_dir / "files"
    existing = find_vhost_conflict(name)
    if existing:
        return False, f"Ya existe un vhost llamado {existing}; elimínalo o renómbralo antes de restaurar"
    folder_conflict = find_folder_conflict(project_dir.parent, project_dir.name) if files_dir.exists() else None
    if folder_conflict:
        return False, f"Ya existe la carpeta {folder_conflict}; muévela antes de restaurar"

    files_restored = False
    if files_dir.exists():
        project_dir.parent.mkdir(parents=True, exist_ok=True)
        files_restored = _run_sudo(["mv", str(files_dir), str(project_dir)])

    certs_bak = item_dir / "certs"
    if certs_bak.exists():
        CERTS_DIR.mkdir(parents=True, exist_ok=True)
        for cert_file in certs_bak.iterdir():
            (CERTS_DIR / cert_file.name).write_bytes(cert_file.read_bytes())

    conf_backup = item_dir / "vhost.conf"
    if conf_backup.exists():
        _sudo_write_file(str(vhost_config_path(name)), conf_backup.read_text())
    else:
        _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, str(project_dir)))

    nginx_conf_backup = item_dir / "vhost-nginx.conf"
    if nginx_conf_backup.exists():
        _sudo_write_file(str(nginx.vhost_config_path(name)), nginx_conf_backup.read_text())
    else:
        nginx.write_vhost_config(name, str(project_dir))

    add_hosts_entry(f"{name}.test")
    _run_sudo(["a2ensite", f"{name}.test.conf"])
    _run_sudo(["systemctl", "reload", "apache2"])
    nginx.enable_site(f"{name}.test.conf")
    nginx.reload()

    # Solo se ajustan permisos si se han devuelto archivos: si la carpeta nunca
    # se movió a la papelera, project_dir puede ser una ruta ajena al proyecto
    if files_restored:
        user = getpass.getuser()
        _run_sudo(["chown", "-R", f"{user}:www-data", str(project_dir)])
        _run_sudo(["chmod", "-R", "ug+rwX", str(project_dir)])
        _run_sudo(["find", str(project_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"])

    db_dump = item_dir / "database.sql"
    if db_dump.exists() and is_command_installed("mysql"):
        _run_sudo_feed(["mysql"], db_dump.read_text())

    _run_sudo(["rm", "-rf", str(item_dir)])
    generate_index_page()
    return True, ""


def purge_trash_item(trash_id: str) -> bool:
    item_dir = TRASH_DIR / trash_id
    if item_dir.exists():
        _run_sudo(["rm", "-rf", str(item_dir)])
    return True


def purge_all_trash() -> bool:
    items = list_trash()
    ok = True
    for meta in items:
        if not purge_trash_item(meta["trash_id"]):
            ok = False
    return ok
