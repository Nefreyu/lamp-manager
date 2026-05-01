import getpass
import os
import shutil
from pathlib import Path
from services.systemd import _run_sudo, _sudo_write_file

HOSTS_FILE = Path("/etc/hosts")
HOSTS_MARKER = "# lamp-manager"
APACHE_SITES_AVAILABLE = Path("/etc/apache2/sites-available")
APACHE_SITES_ENABLED = Path("/etc/apache2/sites-enabled")
INDEX_PAGE = Path("/var/www/html/index.html")


def list_projects(projects_dir: str) -> list[str]:
    base = Path(projects_dir)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def vhost_config_path(name: str) -> Path:
    return APACHE_SITES_AVAILABLE / f"{name}.test.conf"


def vhost_is_enabled(name: str) -> bool:
    return (APACHE_SITES_ENABLED / f"{name}.test.conf").exists()


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
    projects = list_projects(projects_dir)
    if projects:
        items = "\n".join(
            f'        <li><a href="http://{p}.test" target="_blank">{p}.test</a></li>'
            for p in projects
        )
    else:
        items = '        <li class="empty">No hay proyectos todavía.</li>'

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


def create_vhost(name: str, projects_dir: str) -> bool:
    docroot = str(Path(projects_dir) / name)
    config = f"""<VirtualHost *:80>
    ServerName {name}.test
    DocumentRoot {docroot}
    <Directory {docroot}>
        AllowOverride All
        Require all granted
    </Directory>
</VirtualHost>
"""
    if not _sudo_write_file(str(vhost_config_path(name)), config):
        return False
    base_dir = Path(projects_dir)
    if base_dir.exists() and not os.access(base_dir, os.W_OK):
        user = getpass.getuser()
        _run_sudo(["chown", "-R", f"{user}:{user}", str(base_dir)])
    Path(docroot).mkdir(parents=True, exist_ok=True)
    if not add_hosts_entry(f"{name}.test"):
        return False
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
    generate_index_page(projects_dir)
    return True


def enable_vhost(name: str) -> bool:
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def disable_vhost(name: str) -> bool:
    if not _run_sudo(["a2dissite", f"{name}.test.conf"]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])
