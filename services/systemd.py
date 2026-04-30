import subprocess


SERVICES = [
    {"id": "apache2",      "label": "Apache2"},
    {"id": "mysql",        "label": "MySQL"},
    {"id": "php8.5-fpm",   "label": "PHP 8.5-FPM"},
    {"id": "mailpit",      "label": "Mailpit"},
]

_sudo_password: str | None = None


def set_password(password: str):
    global _sudo_password
    _sudo_password = password


def validate_password(password: str) -> bool:
    """Valida la contraseña ejecutando un comando sudo inocuo."""
    result = subprocess.run(
        ["sudo", "-S", "true"],
        input=password + "\n",
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def _run_sudo(command: list) -> bool:
    if _sudo_password is None:
        return False
    
    result = subprocess.run(
        ["sudo", "-S"] + command,
        input=_sudo_password + "\n",
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def get_status(service_id: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", service_id],
        capture_output=True,
        text=True
    )
    return result.stdout.strip() == "active"


def start_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "start", service_id])


def stop_service(service_id: str) -> bool:
    return _run_sudo(["systemctl", "stop", service_id])