import configparser
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "lamp-manager"
CONFIG_FILE = CONFIG_DIR / "config.ini"

DEFAULTS = {
    "mailpit": {
        "storage_enabled": "false",
        "storage_path": "/var/lib/mailpit/mailpit.db",
        "smtp_port": "1025",
        "max_messages": "500",
    },
    "general": {
        "projects_dir": str(Path.home() / "www"),
        "minimize_to_tray": "true",
    }
}


def load() -> configparser.ConfigParser:
    """Carga la configuración desde disco. Si no existe, la crea con valores por defecto."""
    config = configparser.ConfigParser()
    config.read_dict(DEFAULTS)

    if CONFIG_FILE.exists():
        config.read(CONFIG_FILE)

    return config


def save(config: configparser.ConfigParser):
    """Guarda la configuración en disco."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def get(section: str, key: str) -> str:
    config = load()
    return config.get(section, key)


def set(section: str, key: str, value: str):
    config = load()
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, value)
    save(config)