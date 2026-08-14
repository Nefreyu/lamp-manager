import re
import subprocess
from pathlib import Path
import services.systemd as _systemd
from services.systemd import _run_sudo, _sudo_write_file
from services.php import get_installed_version
from config import settings

SITES_AVAILABLE = Path("/etc/nginx/sites-available")
SITES_ENABLED = Path("/etc/nginx/sites-enabled")

NGINX_ERROR_LOG = "/var/log/nginx/error.log"
NGINX_ACCESS_LOG = "/var/log/nginx/access.log"
VHOST_ERROR_LOG = "/var/log/nginx/{name}.test-error.log"
VHOST_ACCESS_LOG = "/var/log/nginx/{name}.test-access.log"

CERTS_DIR = Path.home() / ".local/share/lamp-manager/certs"

DEFAULT_SITE_NAME = "000-default-lamp"
SNAKEOIL_CERT = "/etc/ssl/certs/ssl-cert-snakeoil.pem"
SNAKEOIL_KEY = "/etc/ssl/private/ssl-cert-snakeoil.key"

_PHP_VERSIONS = ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0"]


def get_http_port() -> int:
    return int(settings.get("nginx", "http_port"))


def get_https_port() -> int:
    return int(settings.get("nginx", "https_port"))


def get_version() -> str | None:
    try:
        result = subprocess.run(["nginx", "-v"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    output = result.stderr or result.stdout
    m = re.search(r"nginx/(\S+)", output)
    return m.group(1) if m else None


def configtest() -> tuple[bool, str]:
    if _systemd._sudo_password is None:
        return False, "No hay contraseña configurada"
    result = subprocess.run(
        ["sudo", "-S", "-p", "", "nginx", "-t"],
        input=_systemd._sudo_password + "\n",
        capture_output=True, text=True,
    )
    output = (result.stderr or result.stdout).strip()
    return result.returncode == 0, output


def reload() -> bool:
    return _run_sudo(["systemctl", "reload", "nginx"])


def _php_fpm_socket() -> str:
    ver = get_installed_version() or _PHP_VERSIONS[0]
    return f"/run/php/php{ver}-fpm.sock"


def vhost_config_path(name: str) -> Path:
    return SITES_AVAILABLE / f"{name}.test.conf"


def site_is_enabled(name: str) -> bool:
    return (SITES_ENABLED / f"{name}.test.conf").exists()


def _php_location(socket: str) -> str:
    return f"""    location ~ \\.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:{socket};
    }}"""


def _vhost_config(name: str, docroot: str, https: bool = False) -> str:
    socket = _php_fpm_socket()
    error_log = VHOST_ERROR_LOG.format(name=name)
    access_log = VHOST_ACCESS_LOG.format(name=name)
    php_location = _php_location(socket)
    http_port = get_http_port()
    https_port = get_https_port()

    common_locations = f"""    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

{php_location}

    location ~ /\\.ht {{
        deny all;
    }}"""

    if https:
        return f"""server {{
    listen {http_port};
    server_name {name}.test;
    return 301 https://{name}.test:{https_port}$request_uri;
}}

server {{
    listen {https_port} ssl;
    server_name {name}.test;
    root {docroot};
    index index.php index.html;

    ssl_certificate     {CERTS_DIR}/{name}.test.pem;
    ssl_certificate_key {CERTS_DIR}/{name}.test-key.pem;

    access_log {access_log};
    error_log  {error_log};

{common_locations}
}}
"""
    return f"""server {{
    listen {http_port};
    server_name {name}.test;
    root {docroot};
    index index.php index.html;

    access_log {access_log};
    error_log  {error_log};

{common_locations}
}}
"""


def write_vhost_config(name: str, docroot: str, https: bool = False) -> bool:
    return _sudo_write_file(str(vhost_config_path(name)), _vhost_config(name, docroot, https))


def remove_vhost_config(name: str) -> bool:
    return _run_sudo(["rm", "-f", str(vhost_config_path(name))])


def enable_site(conf_filename: str) -> bool:
    return _run_sudo([
        "ln", "-sf",
        str(SITES_AVAILABLE / conf_filename),
        str(SITES_ENABLED / conf_filename),
    ])


def disable_site(conf_filename: str) -> bool:
    return _run_sudo(["rm", "-f", str(SITES_ENABLED / conf_filename)])


def _default_site_config() -> str:
    return f"""server {{
    listen {get_http_port()} default_server;
    server_name _;
    root /var/www/html;
    index index.html;
}}

server {{
    listen {get_https_port()} ssl default_server;
    server_name _;
    root /var/www/html;
    index index.html;
    ssl_certificate     {SNAKEOIL_CERT};
    ssl_certificate_key {SNAKEOIL_KEY};
}}
"""


def ensure_default_site() -> bool:
    disable_site("default")
    conf_path = SITES_AVAILABLE / f"{DEFAULT_SITE_NAME}.conf"
    if not _sudo_write_file(str(conf_path), _default_site_config()):
        return False
    if not enable_site(f"{DEFAULT_SITE_NAME}.conf"):
        return False
    # restart (no reload): tras la instalación del paquete, nginx.service puede
    # estar en "failed" por el conflicto de puerto con el default de fábrica —
    # reload no arranca un servicio parado/fallido, restart sí.
    return _run_sudo(["systemctl", "restart", "nginx"])
