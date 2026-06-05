import logging
from pathlib import Path

log = logging.getLogger(__name__)

_AUTOSTART_FILE = Path.home() / ".config/autostart/io.github.nefreyu.LampManager.desktop"
_APPS_DESKTOP   = Path.home() / ".local/share/applications/io.github.nefreyu.LampManager.desktop"
_SYSTEM_DESKTOP = Path("/usr/share/applications/io.github.nefreyu.LampManager.desktop")


def _get_exec_line() -> str:
    for desktop in (_APPS_DESKTOP, _SYSTEM_DESKTOP):
        if desktop.exists():
            for line in desktop.read_text().splitlines():
                if line.startswith("Exec="):
                    return line.split("=", 1)[1]
    return "lamp-manager"


def is_enabled() -> bool:
    return _AUTOSTART_FILE.exists()


def enable():
    try:
        _AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AUTOSTART_FILE.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=LAMP Manager\n"
            f"Exec={_get_exec_line()} --autostart\n"
            "Icon=io.github.nefreyu.LampManager\n"
            "Terminal=false\n"
            "Hidden=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    except Exception as e:
        log.error("No se pudo crear el archivo de autoarranque: %s", e)


def disable():
    try:
        _AUTOSTART_FILE.unlink(missing_ok=True)
    except Exception as e:
        log.error("No se pudo eliminar el archivo de autoarranque: %s", e)
