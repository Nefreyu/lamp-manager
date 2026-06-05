import gi
import os
import sys
import logging
from pathlib import Path

from config import log as _log_setup
_log_setup.setup()

try:
    from config.dev import DEV_MODE, SKIP_PASSWORD_DIALOG
except ImportError:
    DEV_MODE = False
    SKIP_PASSWORD_DIALOG = False

gtk_modules = os.environ.get("GTK_MODULES", "")
filtered = ":".join(m for m in gtk_modules.split(":") if m and m != "atk-bridge")
os.environ["GTK_MODULES"] = filtered

# Instalar iconos en ~/.local/share/icons/ si se ejecuta desde el directorio de desarrollo
_icon_src = Path(__file__).parent / "packaging/icons/hicolor/scalable/apps/io.github.nefreyu.LampManager.svg"
if _icon_src.exists():
    import subprocess
    _hicolor = Path.home() / ".local/share/icons/hicolor"
    _icons_dst_dir = _hicolor / "scalable/apps"
    _icons_dst_dir.mkdir(parents=True, exist_ok=True)
    _new_icons = False
    for _svg in (_icon_src.parent).glob("*.svg"):
        _dst = _icons_dst_dir / _svg.name
        if not _dst.exists():
            _dst.symlink_to(_svg.resolve())
            _new_icons = True
    _icon_dst = _icons_dst_dir / "io.github.nefreyu.LampManager.svg"
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
        _new_icons = True
    if _new_icons:
        subprocess.run(["gtk-update-icon-cache", "-f", str(_hicolor)], capture_output=True)

# Instalar .desktop en ~/.local/share/applications/ si se ejecuta desde el directorio de desarrollo
_desktop_src = Path(__file__).parent / "packaging/io.github.nefreyu.LampManager.desktop"
if _desktop_src.exists():
    import subprocess
    _apps_dir = Path.home() / ".local/share/applications"
    _apps_dir.mkdir(parents=True, exist_ok=True)
    _desktop_dst = _apps_dir / "io.github.nefreyu.LampManager.desktop"
    _desktop_content = _desktop_src.read_text()
    _exec_line = f"Exec=python3 {Path(__file__).resolve()}"
    _desktop_content = "\n".join(
        _exec_line if line.startswith("Exec=") else line
        for line in _desktop_content.splitlines()
    ) + "\n"
    if not _desktop_dst.exists() or _desktop_dst.read_text() != _desktop_content:
        _desktop_dst.write_text(_desktop_content)
        subprocess.run(["update-desktop-database", str(_apps_dir)], capture_output=True)

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Gdk, Adw

GLib.set_prgname("io.github.nefreyu.LampManager")
GLib.set_application_name("LAMP Manager")

from windows.main_window import MainWindow
from windows.splash_window import SplashWindow
from services.tray import SystemTray
from services.keyring import get_sudo_password
from services.systemd import validate_password, set_password


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.nefreyu.LampManager")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self._autostart = "--autostart" in sys.argv
        self._window = MainWindow(self)
        self._splash = SplashWindow(app)
        self._splash.present()
        self._splash_start = GLib.get_monotonic_time()
        GLib.idle_add(self._build_main)

    def _build_main(self):
        elapsed_ms = (GLib.get_monotonic_time() - self._splash_start) // 1000
        remaining = max(0, 1200 - elapsed_ms)
        GLib.timeout_add(remaining, self._show_silent if self._autostart else self._show_main)
        return False

    def _show_main(self):
        self._window.present()
        GLib.idle_add(self._splash.close)
        if not (DEV_MODE and SKIP_PASSWORD_DIALOG):
            GLib.idle_add(self._window.request_password)
        self._setup_tray(window_visible=True)
        return False

    def _show_silent(self):
        GLib.idle_add(self._splash.close)
        stored = get_sudo_password()
        if stored and validate_password(stored):
            set_password(stored)
            self._setup_tray(window_visible=False)
        else:
            self._window.present()
            if not (DEV_MODE and SKIP_PASSWORD_DIALOG):
                GLib.idle_add(self._window.request_password)
            self._setup_tray(window_visible=True)
        return False

    def _setup_tray(self, window_visible: bool):
        def _toggle():
            self._window.toggle_visibility()
            self._tray.set_window_visible(self._window.is_visible())
        self._tray = SystemTray(_toggle, self.quit)
        self._tray.start()
        self._window.connect("hide", lambda *_: self._tray.set_window_visible(False))
        self._tray.set_window_visible(window_visible)
            

if __name__ == "__main__":
    app = App()
    app.run()