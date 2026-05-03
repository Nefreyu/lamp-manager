from pathlib import Path

RECOMMENDATIONS = [
    {
        "id": "apache2",
        "label": "Apache",
        "description": "Servidor web necesario para servir las aplicaciones PHP.",
        "checks": ["/usr/sbin/apache2"],
        "commands": [
            {"label": "Apache", "cmd": "sudo apt install apache2"},
        ],
    },
    {
        "id": "php-fpm",
        "label": "PHP-FPM",
        "description": "Procesador PHP necesario para ejecutar aplicaciones web.",
        "checks": [f"/usr/sbin/php-fpm{ver}" for ver in ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0"]],
        "commands": [
            {"label": "PHP-FPM", "cmd": "sudo apt install php-fpm"},
        ],
    },
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
    {
        "id": "mailpit",
        "label": "Mailpit",
        "description": "Captura los correos enviados por las aplicaciones PHP para revisarlos sin enviarlos realmente.",
        "checks": ["/usr/local/bin/mailpit"],
        "commands": [
            {"label": "Mailpit", "cmd": "sudo apt install mailpit"},
        ],
    },
]


def _is_satisfied(rec: dict) -> bool:
    return any(Path(p).exists() for p in rec["checks"])


def get_missing() -> list[dict]:
    return [r for r in RECOMMENDATIONS if not _is_satisfied(r)]
