import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from windows.main_window import MainWindow


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.example.lampmanager")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        window = MainWindow(app)
        window.present()
        GLib.idle_add(window.request_password)


if __name__ == "__main__":
    app = App()
    app.run()