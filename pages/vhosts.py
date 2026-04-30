import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class VHostsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        label = Gtk.Label()
        label.set_markup("<span size='x-large' weight='bold'>Virtual Hosts</span>")
        self.append(label)

        sublabel = Gtk.Label(label="Aquí irá la gestión de virtual hosts...")
        self.append(sublabel)