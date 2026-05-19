import re
import subprocess
from pathlib import Path
import services.systemd as _systemd

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


_SYSTEM_DBS = {"information_schema", "performance_schema", "mysql", "sys", "phpmyadmin"}
_last_error: list[str] = [""]
_HIDDEN_USERS = {
    "root", "mysql.sys", "mysql.infoschema",
    "mysql.session", "debian-sys-maint",
    "phpmyadmin", "admin",
}


def _query(sql: str) -> str | None:
    if _systemd._sudo_password is None:
        return None
    import subprocess
    result = subprocess.run(
        ["sudo", "-S", "-p", "", "mysql", "--batch", "--skip-column-names", "-e", sql],
        input=_systemd._sudo_password + "\n",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _last_error[0] = (result.stderr or result.stdout).strip()
        return None
    return result.stdout


def _exec(sql: str) -> bool:
    return _systemd._run_sudo(["mysql", "-e", sql])


def list_databases() -> list[str] | None:
    out = _query("SHOW DATABASES;")
    if out is None:
        return None
    return [db for db in out.splitlines() if db and db not in _SYSTEM_DBS]


def get_last_error() -> str:
    return _last_error[0]


def create_database(name: str) -> bool:
    safe = name.replace("`", "").replace("'", "")
    return _exec(f"CREATE DATABASE `{safe}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")


def drop_database(name: str) -> bool:
    safe = name.replace("`", "").replace("'", "")
    return _exec(f"DROP DATABASE `{safe}`;")


def list_users() -> list[tuple[str, str]]:
    hidden = ", ".join(f"'{u}'" for u in _HIDDEN_USERS)
    out = _query(
        f"SELECT user, host FROM mysql.user "
        f"WHERE user NOT IN ({hidden}) ORDER BY user, host;"
    )
    if out is None:
        return []
    result = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0]:
            result.append((parts[0], parts[1]))
    return result


def create_user(username: str, host: str, password: str) -> bool:
    u = username.replace("'", "")
    h = host.replace("'", "")
    p = password.replace("'", "")
    return _exec(f"CREATE USER '{u}'@'{h}' IDENTIFIED BY '{p}';")


def drop_user(username: str, host: str) -> bool:
    u = username.replace("'", "")
    h = host.replace("'", "")
    ok = _exec(f"DROP USER '{u}'@'{h}';")
    if ok:
        _exec("FLUSH PRIVILEGES;")
    return ok


def grant_all(username: str, host: str, database: str) -> bool:
    u = username.replace("'", "")
    h = host.replace("'", "")
    db = database.replace("`", "")
    ok = _exec(f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{u}'@'{h}';")
    if ok:
        _exec("FLUSH PRIVILEGES;")
    return ok


def get_version() -> str | None:
    try:
        result = subprocess.run(["mysql", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode == 0:
        m = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if m:
            return m.group(1)
    return None
