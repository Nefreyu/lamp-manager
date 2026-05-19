import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


class SplashWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(260, 180)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_margin_top(32)
        outer.set_margin_bottom(32)
        outer.set_margin_start(40)
        outer.set_margin_end(40)

        icon = Gtk.Image.new_from_icon_name("io.github.nefreyu.LampManager")
        icon.set_pixel_size(72)
        icon.set_margin_bottom(12)
        outer.append(icon)

        name_label = Gtk.Label()
        name_label.set_markup("<span size='large' weight='bold'>LAMP Manager</span>")
        name_label.set_margin_bottom(16)
        outer.append(name_label)

        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(24, 24)
        self._spinner.start()
        outer.append(self._spinner)

        self.set_child(outer)
