import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="LAMP Manager")
        self.set_default_size(800, 600)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        self.set_child(box)

        label = Gtk.Label()
        label.set_markup("<span size='x-large' weight='bold'>¡Hola desde GTK4!</span>")
        box.append(label)

        button = Gtk.Button(label="Púlsame")
        button.connect("clicked", self.on_button_clicked)
        box.append(button)

        self.response_label = Gtk.Label(label="")
        box.append(self.response_label)

    def on_button_clicked(self, button):
        self.response_label.set_text("¡GTK4 funciona correctamente!")


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.example.lampmanager")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        window = MainWindow(app)
        window.present()


if __name__ == "__main__":
    app = App()
    app.run()