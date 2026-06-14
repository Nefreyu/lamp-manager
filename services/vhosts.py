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
from pathlib import Path
from services.systemd import _run_sudo, _sudo_write_file, _run_sudo_output, _run_sudo_feed

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
        return True, None
    except Exception as e:
        log.error("Error al crear el proyecto '%s': %s", name, e)
        return False, str(e)

HOSTS_FILE = Path("/etc/hosts")
HOSTS_MARKER = "# lamp-manager"
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


def list_orphan_folders(projects_dir: str) -> list[str]:
    existing = set(list_projects())
    base = Path(projects_dir)
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and d.name not in existing
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

    if https:
        return f"""<VirtualHost *:80>
    ServerName {name}.test
    Redirect permanent / https://{name}.test/
</VirtualHost>

<VirtualHost *:443>
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
    return f"""<VirtualHost *:80>
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
    if not conf.exists():
        content = """<VirtualHost *:443>
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
    return _run_sudo(["systemctl", "reload", "apache2"])


def disable_https(name: str) -> bool:
    (CERTS_DIR / f"{name}.test.pem").unlink(missing_ok=True)
    (CERTS_DIR / f"{name}.test-key.pem").unlink(missing_ok=True)
    docroot = get_docroot(name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https=False)):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def add_hosts_entry(domain: str) -> bool:
    current = HOSTS_FILE.read_text()
    if domain in current:
        return True
    new_content = current.rstrip("\n") + f"\n127.0.0.1\t{domain}\t{HOSTS_MARKER}\n"
    return _sudo_write_file(str(HOSTS_FILE), new_content)


def remove_hosts_entry(domain: str) -> bool:
    current = HOSTS_FILE.read_text()
    lines = [l for l in current.splitlines(keepends=True) if domain not in l]
    return _sudo_write_file(str(HOSTS_FILE), "".join(lines))


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
        "laravel":   ("Laravel",    "fw-laravel"),
        "symfony":   ("Symfony",    "fw-symfony"),
        "wordpress": ("WordPress",  "fw-wordpress"),
        "php":       ("PHP",        "fw-php"),
    }

    _ICON_GLOBE = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
    _ICON_FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    _ICON_CODE   = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'

    def _card(name):
        docroot  = get_docroot(name)
        has_https = vhost_has_https(name)
        fw_id    = detect_framework(docroot)
        fw_label, fw_cls = _FW_LABELS[fw_id]
        protocol = "https" if has_https else "http"
        domain   = f"{name}.test"
        https_badge = (
            '<span class="badge badge-https">HTTPS</span>'
            if has_https else
            '<span class="badge badge-http">HTTP</span>'
        )
        return f"""      <div class="card">
        <div class="card-header">
          <span class="card-name">{name}</span>
          {https_badge}
        </div>
        <div class="card-info">
          <div class="info-row">{_ICON_GLOBE}<span class="value">{domain}</span></div>
          <div class="info-row">{_ICON_CODE}<span class="fw-badge {fw_cls}">{fw_label}</span></div>
          <div class="info-row">{_ICON_FOLDER}<span class="value docroot">{docroot}</span></div>
        </div>
        <a href="{protocol}://{domain}" target="_blank" class="card-link">Abrir proyecto →</a>
      </div>"""

    cards = "\n".join(_card(p) for p in projects)
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
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 18px 32px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .header-dot {{
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--accent);
      flex-shrink: 0;
    }}
    header h1 {{ font-size: 1.1rem; font-weight: 600; }}
    .header-count {{
      margin-left: auto;
      font-size: 0.82rem;
      color: var(--text-muted);
    }}
    main {{ padding: 32px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 22px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      transition: border-color 0.2s, transform 0.15s;
    }}
    .card:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .card-name {{ font-size: 1.05rem; font-weight: 600; }}
    .badge {{
      font-size: 0.7rem; font-weight: 600;
      padding: 3px 8px; border-radius: 20px;
      text-transform: uppercase; letter-spacing: 0.05em;
      flex-shrink: 0;
    }}
    .badge-https {{ background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }}
    .badge-http  {{ background: rgba(148,163,184,0.1); color: #94a3b8; border: 1px solid rgba(148,163,184,0.2); }}
    .card-info {{ display: flex; flex-direction: column; gap: 9px; flex: 1; }}
    .info-row {{
      display: flex; align-items: center; gap: 8px;
      font-size: 0.85rem; color: var(--text-muted);
    }}
    .info-row svg {{ flex-shrink: 0; }}
    .value {{ color: var(--text); word-break: break-all; }}
    .docroot {{ font-size: 0.78rem; color: var(--text-muted); }}
    .fw-badge {{
      font-size: 0.72rem; font-weight: 600;
      padding: 2px 9px; border-radius: 4px;
      text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .fw-laravel   {{ background: rgba(255,75,75,0.15);  color: #f87171; border: 1px solid rgba(255,75,75,0.3); }}
    .fw-symfony   {{ background: rgba(0,210,180,0.12);  color: #2dd4bf; border: 1px solid rgba(0,210,180,0.3); }}
    .fw-wordpress {{ background: rgba(96,165,250,0.12); color: #60a5fa; border: 1px solid rgba(96,165,250,0.3); }}
    .fw-php       {{ background: rgba(167,139,250,0.12);color: #a78bfa; border: 1px solid rgba(167,139,250,0.3); }}
    .card-link {{
      display: block; text-align: center;
      padding: 9px 16px;
      background: var(--accent); color: white;
      text-decoration: none; border-radius: 8px;
      font-size: 0.875rem; font-weight: 500;
      transition: background 0.15s;
    }}
    .card-link:hover {{ background: var(--accent-hover); }}
    footer {{
      text-align: center; padding: 24px;
      color: var(--text-muted); font-size: 0.78rem;
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-dot"></div>
    <h1>LAMP Manager</h1>
    <span class="header-count">{count} {plural}</span>
  </header>
  <main>
    <div class="grid">
{cards}
    </div>
  </main>
  <footer>LAMP Manager &middot; entorno local</footer>
</body>
</html>
"""
    return _sudo_write_file(str(INDEX_PAGE), html)


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


def get_docroot(name: str) -> str:
    config = vhost_config_path(name)
    if not config.exists():
        return ""
    content = _run_sudo_output(["cat", str(config)])
    if not content:
        return ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("DocumentRoot "):
            return stripped[len("DocumentRoot "):].strip()
    return ""


def update_docroot(name: str, new_docroot: str) -> bool:
    config = vhost_config_path(name)
    if not config.exists():
        return False
    lines = []
    for line in config.read_text().splitlines():
        stripped = line.strip()
        indent = " " * (len(line) - len(line.lstrip()))
        if stripped.startswith("DocumentRoot "):
            lines.append(f"{indent}DocumentRoot {new_docroot}")
        elif stripped.startswith("<Directory ") and stripped.endswith(">"):
            lines.append(f"{indent}<Directory {new_docroot}>")
        else:
            lines.append(line)
    if not _sudo_write_file(str(config), "\n".join(lines) + "\n"):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def _detect_docroot(projects_dir: str, name: str) -> str:
    base = Path(projects_dir) / name
    public = base / "public"
    return str(public) if public.is_dir() else str(base)


def create_vhost(name: str, projects_dir: str) -> bool:
    docroot = _detect_docroot(projects_dir, name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot)):
        return False
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


def delete_vhost(name: str, projects_dir: str) -> bool:
    _run_sudo(["a2dissite", f"{name}.test.conf"])
    _run_sudo(["rm", "-f", str(vhost_config_path(name))])
    remove_hosts_entry(f"{name}.test")
    _run_sudo(["systemctl", "reload", "apache2"])
    project_dir = Path(projects_dir) / name
    if project_dir.exists():
        _run_sudo(["rm", "-rf", str(project_dir)])
    disable_https(name)
    generate_index_page()
    return True


def enable_vhost(name: str) -> bool:
    if not add_hosts_entry(f"{name}.test"):
        return False
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    generate_index_page()
    return True


def disable_vhost(name: str) -> bool:
    if not _run_sudo(["a2dissite", f"{name}.test.conf"]):
        return False
    remove_hosts_entry(f"{name}.test")
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    generate_index_page()
    return True


def _project_dir_from_docroot(docroot: str) -> Path | None:
    if not docroot:
        return None
    p = Path(docroot)
    return p.parent if p.name == "public" else p


def trash_vhost(name: str) -> bool:
    trash_id = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    item_dir = TRASH_DIR / trash_id
    item_dir.mkdir(parents=True, exist_ok=True)

    project_dir = _project_dir_from_docroot(get_docroot(name))

    meta = {
        "trash_id": trash_id,
        "name": name,
        "project_dir": str(project_dir) if project_dir else None,
        "deleted_at": datetime.now().isoformat(),
        "has_db": False,
    }

    config_content = _run_sudo_output(["cat", str(vhost_config_path(name))])
    if config_content:
        (item_dir / "vhost.conf").write_text(config_content)

    _run_sudo(["a2dissite", f"{name}.test.conf"])
    remove_hosts_entry(f"{name}.test")
    _run_sudo(["systemctl", "reload", "apache2"])
    _run_sudo(["rm", "-f", str(vhost_config_path(name))])

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

    if project_dir and project_dir.exists():
        _run_sudo(["mv", str(project_dir), str(item_dir / "files")])

    logs_bak = item_dir / "logs"
    for log_path in (VHOST_ERROR_LOG.format(name=name), VHOST_ACCESS_LOG.format(name=name)):
        if Path(log_path).exists():
            logs_bak.mkdir(exist_ok=True)
            _run_sudo(["mv", log_path, str(logs_bak / Path(log_path).name)])

    (item_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    generate_index_page()
    return True


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


def restore_vhost(trash_id: str) -> bool:
    item_dir = TRASH_DIR / trash_id
    meta_path = item_dir / "meta.json"
    if not meta_path.exists():
        return False

    meta = json.loads(meta_path.read_text())
    name = meta["name"]

    if meta.get("project_dir"):
        project_dir = Path(meta["project_dir"])
    else:
        project_dir = Path(meta["projects_dir"]) / name

    files_dir = item_dir / "files"
    if files_dir.exists():
        project_dir.parent.mkdir(parents=True, exist_ok=True)
        _run_sudo(["mv", str(files_dir), str(project_dir)])

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

    add_hosts_entry(f"{name}.test")
    _run_sudo(["a2ensite", f"{name}.test.conf"])
    _run_sudo(["systemctl", "reload", "apache2"])

    if project_dir.exists():
        user = getpass.getuser()
        _run_sudo(["chown", "-R", f"{user}:www-data", str(project_dir)])
        _run_sudo(["chmod", "-R", "ug+rwX", str(project_dir)])
        _run_sudo(["find", str(project_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"])

    db_dump = item_dir / "database.sql"
    if db_dump.exists() and is_command_installed("mysql"):
        _run_sudo_feed(["mysql"], db_dump.read_text())

    _run_sudo(["rm", "-rf", str(item_dir)])
    generate_index_page()
    return True


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
