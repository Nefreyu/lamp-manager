import gi
import os
try:
    from config.dev import DEV_MODE, SKIP_PASSWORD_DIALOG
except ImportError:
    DEV_MODE = False
    SKIP_PASSWORD_DIALOG = False

gtk_modules = os.environ.get("GTK_MODULES", "")
filtered = ":".join(m for m in gtk_modules.split(":") if m and m != "atk-bridge")
os.environ["GTK_MODULES"] = filtered

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from windows.main_window import MainWindow


class App(Gtk.Application):
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