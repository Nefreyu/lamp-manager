import gi
import os
from pathlib import Path

try:
    from config.dev import DEV_MODE, SKIP_PASSWORD_DIALOG
except ImportError:
    DEV_MODE = False
    SKIP_PASSWORD_DIALOG = False

gtk_modules = os.environ.get("GTK_MODULES", "")
filtered = ":".join(m for m in gtk_modules.split(":") if m and m != "atk-bridge")
os.environ["GTK_MODULES"] = filtered

# Instalar icono en ~/.local/share/icons/ si se ejecuta desde el directorio de desarrollo
_icon_src = Path(__file__).parent / "packaging/icons/hicolor/scalable/apps/io.github.nefreyu.LampManager.svg"
if _icon_src.exists():
    import subprocess
    _hicolor = Path.home() / ".local/share/icons/hicolor"
    _icon_dst = _hicolor / "scalable/apps/io.github.nefreyu.LampManager.svg"
    _icon_dst.parent.mkdir(parents=True, exist_ok=True)
    if not _icon_dst.exists():
        _icon_dst.symlink_to(_icon_src.resolve())
    _index = _hicolor / "index.theme"
    _content = _index.read_text() if _index.exists() else ""
    if "scalable/apps" not in _content:
        if "Directories=" in _content:
            _content = _content.replace(
                next(l for l in _content.splitlines() if l.startswith("Directories=")),
                next(l for l in _content.splitlines() if l.startswith("Directories=")) + ",scalable/apps"
            )
            _content = _content.rstrip() + "\n\n[scalable/apps]\nSize=48\nType=Scalable\nMinSize=1\nMaxSize=256\n"
        else:
            _content = (
                "[Icon Theme]\nName=Hicolor\nComment=Hicolor icon theme\nDirectories=scalable/apps\n\n"
                "[scalable/apps]\nSize=48\nType=Scalable\nMinSize=1\nMaxSize=256\n"
            )
        _index.write_text(_content)
        subprocess.run(["gtk-update-icon-cache", "-f", str(_hicolor)], capture_output=True)

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Gdk, Adw

from windows.main_window import MainWindow


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.nefreyu.LampManager")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        window = MainWindow(app)
        window.set_startup_id(app.get_application_id())
        window.present()
        if not (DEV_MODE and SKIP_PASSWORD_DIALOG):
            GLib.idle_add(window.request_password)
            

if __name__ == "__main__":
    app = App()
    app.run()