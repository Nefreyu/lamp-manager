from pathlib import Path

RECOMMENDATIONS = [
    {
        "id": "db-server",
        "label": "Servidor de base de datos",
        "description": "MySQL o MariaDB son necesarios para ejecutar aplicaciones PHP con base de datos.",
        "checks": ["/usr/sbin/mysqld", "/usr/sbin/mariadbd"],
        "commands": [
            {"label": "MySQL",   "cmd": "sudo apt install mysql-server"},
            {"label": "MariaDB", "cmd": "sudo apt install mariadb-server"},
        ],
    },
    {
        "id": "db-manager",
        "label": "Gestor de base de datos",
        "description": "phpMyAdmin permite administrar las bases de datos desde el navegador.",
        "checks": ["/usr/share/phpmyadmin/index.php"],
        "commands": [
            {"label": "phpMyAdmin", "cmd": "sudo apt install phpmyadmin"},
        ],
    },
]


def _is_satisfied(rec: dict) -> bool:
    return any(Path(p).exists() for p in rec["checks"])


def get_missing() -> list[dict]:
    return [r for r in RECOMMENDATIONS if not _is_satisfied(r)]
