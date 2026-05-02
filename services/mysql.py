import re
import subprocess
from pathlib import Path

_CONF_CANDIDATES = [
    "/etc/mysql/mysql.conf.d/mysqld.cnf",
    "/etc/mysql/mariadb.conf.d/50-server.cnf",
    "/etc/mysql/my.cnf",
]
MYSQL_ERROR_LOG = "/var/log/mysql/error.log"
MYSQL_SLOW_LOG = "/var/log/mysql/mysql-slow.log"


def get_conf_path() -> str:
    for p in _CONF_CANDIDATES:
        if Path(p).exists():
            return p
    return _CONF_CANDIDATES[0]


def get_version() -> str | None:
    result = subprocess.run(["mysql", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        m = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if m:
            return m.group(1)
    return None
