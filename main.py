import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class ServiciosPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        label = Gtk.Label()
        label.set_markup("<span size='x-large' weight='bold'>Servicios</span>")
        self.append(label)

        sublabel = Gtk.Label(label="Aquí irá el estado de Apache, MySQL, Mailpit...")
        self.append(sublabel)


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


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_default_size(800, 500)

        # Header Bar
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title = Gtk.Label(label="LAMP Manager")
        header.set_title_widget(title)

        # Layout principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(main_box)

        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.set_margin_top(12)
        sidebar.set_margin_bottom(12)
        sidebar.set_margin_start(12)
        sidebar.set_margin_end(12)
        sidebar.set_size_request(150, -1)
        main_box.append(sidebar)

        btn_servicios = Gtk.Button(label="Servicios")
        btn_servicios.connect("clicked", self.on_section_changed, "servicios")
        sidebar.append(btn_servicios)

        btn_vhosts = Gtk.Button(label="Virtual Hosts")
        btn_vhosts.connect("clicked", self.on_section_changed, "vhosts")
        sidebar.append(btn_vhosts)

        # Separador
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(separator)

        # Stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_hexpand(True)
        main_box.append(self.stack)

        # Páginas
        self.stack.add_named(ServiciosPage(), "servicios")
        self.stack.add_named(VHostsPage(), "vhosts")

    def on_section_changed(self, button, section):
        self.stack.set_visible_child_name(section)


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