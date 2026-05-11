import getpass
import io
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from services.systemd import _run_sudo, _sudo_write_file, _run_sudo_output

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
        except Exception:
            pass
    else:
        try:
            _FRAMEWORKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _FRAMEWORKS_FILE.write_text(
                json.dumps(_DEFAULT_FRAMEWORKS, indent=2, ensure_ascii=False)
            )
        except Exception:
            pass
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
        return False, str(e)

HOSTS_FILE = Path("/etc/hosts")
HOSTS_MARKER = "# lamp-manager"
APACHE_SITES_AVAILABLE = Path("/etc/apache2/sites-available")
APACHE_SITES_ENABLED = Path("/etc/apache2/sites-enabled")
INDEX_PAGE = Path("/var/www/html/index.html")
INDEX_BACKUP = Path("/var/www/html/index.html.lamp-manager.bak")
CERTS_DIR = Path.home() / ".local/share/lamp-manager/certs"


def list_projects(projects_dir: str) -> list[str]:
    base = Path(projects_dir)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def vhost_config_path(name: str) -> Path:
    return APACHE_SITES_AVAILABLE / f"{name}.test.conf"


def vhost_is_enabled(name: str) -> bool:
    return (APACHE_SITES_ENABLED / f"{name}.test.conf").exists()


def is_mkcert_installed() -> bool:
    result = subprocess.run(["which", "mkcert"], capture_output=True, text=True)
    return result.returncode == 0


def vhost_has_https(name: str) -> bool:
    return (CERTS_DIR / f"{name}.test.pem").exists()


def _vhost_config(name: str, docroot: str, https: bool = False) -> str:
    directory_block = f"""    <Directory {docroot}>
        AllowOverride All
        Require all granted
    </Directory>"""

    if https:
        return f"""<VirtualHost *:80>
    ServerName {name}.test
    Redirect permanent / https://{name}.test/
</VirtualHost>

<VirtualHost *:443>
    ServerName {name}.test
    DocumentRoot {docroot}
    SSLEngine on
    SSLCertificateFile {CERTS_DIR}/{name}.test.pem
    SSLCertificateKeyFile {CERTS_DIR}/{name}.test-key.pem
{directory_block}
</VirtualHost>
"""
    return f"""<VirtualHost *:80>
    ServerName {name}.test
    DocumentRoot {docroot}
{directory_block}
</VirtualHost>
"""


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


def enable_https(name: str, projects_dir: str) -> bool:
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
    docroot = _detect_docroot(projects_dir, name)
    if not _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https=True)):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def disable_https(name: str, projects_dir: str) -> bool:
    (CERTS_DIR / f"{name}.test.pem").unlink(missing_ok=True)
    (CERTS_DIR / f"{name}.test-key.pem").unlink(missing_ok=True)
    docroot = _detect_docroot(projects_dir, name)
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


def generate_index_page(projects_dir: str) -> bool:
    projects = [p for p in list_projects(projects_dir) if vhost_is_enabled(p)]

    if not projects:
        if INDEX_BACKUP.exists():
            _run_sudo(["cp", str(INDEX_BACKUP), str(INDEX_PAGE)])
            _run_sudo(["rm", "-f", str(INDEX_BACKUP)])
        return True

    if INDEX_PAGE.exists() and not INDEX_BACKUP.exists():
        _run_sudo(["cp", str(INDEX_PAGE), str(INDEX_BACKUP)])

    items = "\n".join(
        f'        <li><a href="http://{p}.test" target="_blank">{p}.test</a></li>'
        for p in projects
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LAMP Manager</title>
  <style>
    body {{
      font-family: Cantarell, sans-serif;
      background: #f6f5f4;
      color: #2e2e2e;
      display: flex;
      justify-content: center;
      padding: 48px 16px;
      margin: 0;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.12);
      padding: 32px 40px;
      min-width: 320px;
    }}
    h1 {{ font-size: 1.4rem; margin: 0 0 8px; }}
    p.subtitle {{ color: #777; font-size: 0.9rem; margin: 0 0 24px; }}
    ul {{ list-style: none; padding: 0; margin: 0; }}
    li {{ padding: 10px 0; border-bottom: 1px solid #f0f0f0; }}
    li:last-child {{ border-bottom: none; }}
    a {{ color: #1c71d8; text-decoration: none; font-size: 1rem; }}
    a:hover {{ text-decoration: underline; }}
    li.empty {{ color: #999; font-style: italic; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>LAMP Manager</h1>
    <p class="subtitle">Proyectos disponibles</p>
    <ul>
{items}
    </ul>
  </div>
</body>
</html>
"""
    return _sudo_write_file(str(INDEX_PAGE), html)


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
        _run_sudo(["chown", "-R", f"www-data:{user}", str(project_dir)])
        _run_sudo(["chmod", "-R", "ug+rwX", str(project_dir)])
        _run_sudo(["find", str(project_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"])
    if not add_hosts_entry(f"{name}.test"):
        return False
    _run_sudo(["a2enmod", "rewrite"])
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    _run_sudo(["systemctl", "reload", "apache2"])
    generate_index_page(projects_dir)
    return True


def delete_vhost(name: str, projects_dir: str) -> bool:
    _run_sudo(["a2dissite", f"{name}.test.conf"])
    _run_sudo(["rm", "-f", str(vhost_config_path(name))])
    remove_hosts_entry(f"{name}.test")
    _run_sudo(["systemctl", "reload", "apache2"])
    project_dir = Path(projects_dir) / name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    disable_https(name, projects_dir)
    generate_index_page(projects_dir)
    return True


def enable_vhost(name: str, projects_dir: str) -> bool:
    if not add_hosts_entry(f"{name}.test"):
        return False
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    generate_index_page(projects_dir)
    return True


def disable_vhost(name: str, projects_dir: str) -> bool:
    if not _run_sudo(["a2dissite", f"{name}.test.conf"]):
        return False
    remove_hosts_entry(f"{name}.test")
    if not _run_sudo(["systemctl", "reload", "apache2"]):
        return False
    generate_index_page(projects_dir)
    return True
