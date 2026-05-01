from pathlib import Path
from services.systemd import _run_sudo

HOSTS_FILE = Path("/etc/hosts")
HOSTS_MARKER = "# lamp-manager"
APACHE_SITES_AVAILABLE = Path("/etc/apache2/sites-available")
APACHE_SITES_ENABLED = Path("/etc/apache2/sites-enabled")


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
    entry = f"127.0.0.1\t{domain}\t{HOSTS_MARKER}\n"
    current = HOSTS_FILE.read_text()
    if domain in current:
        return True
    return _run_sudo(["tee", "-a", str(HOSTS_FILE)], stdin=entry)


def remove_hosts_entry(domain: str) -> bool:
    current = HOSTS_FILE.read_text()
    lines = [l for l in current.splitlines(keepends=True) if domain not in l]
    new_content = "".join(lines)
    return _run_sudo(["tee", str(HOSTS_FILE)], stdin=new_content)


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
    config_path = str(vhost_config_path(name))
    if not _run_sudo(["tee", config_path], stdin=config):
        return False
    _run_sudo(["mkdir", "-p", docroot])
    if not add_hosts_entry(f"{name}.test"):
        return False
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def delete_vhost(name: str) -> bool:
    _run_sudo(["a2dissite", f"{name}.test.conf"])
    _run_sudo(["rm", "-f", str(vhost_config_path(name))])
    remove_hosts_entry(f"{name}.test")
    return _run_sudo(["systemctl", "reload", "apache2"])


def enable_vhost(name: str) -> bool:
    if not _run_sudo(["a2ensite", f"{name}.test.conf"]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])


def disable_vhost(name: str) -> bool:
    if not _run_sudo(["a2dissite", f"{name}.test.conf"]):
        return False
    return _run_sudo(["systemctl", "reload", "apache2"])
