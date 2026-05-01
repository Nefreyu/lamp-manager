import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from pages.servicios import ServiciosPage
from pages.vhosts import VHostsPage
from windows.password_dialog import PasswordDialog
from services.systemd import set_password, validate_password
from pages.ajustes import AjustesPage


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_default_size(800, 500)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title = Gtk.Label(label="LAMP Manager")
        header.set_title_widget(title)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(main_box)

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

        btn_ajustes = Gtk.Button(label="Ajustes")
        btn_ajustes.connect("clicked", self.on_section_changed, "ajustes")
        sidebar.append(btn_ajustes)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(separator)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_hexpand(True)
        main_box.append(self.stack)

        self.stack.add_named(ServiciosPage(), "servicios")
        self.stack.add_named(VHostsPage(), "vhosts")
        self.stack.add_named(AjustesPage(), "ajustes")

    def request_password(self):
        self.dialog = PasswordDialog(self, self.on_password_success, self.on_password_cancel)
        self.dialog.present()

    def on_password_success(self, password):
        if validate_password(password):
            set_password(password)
            self.dialog.close()
        else:
            self.dialog.show_error()

    def on_password_cancel(self):
        self.dialog.close()
        self.close()

    def on_section_changed(self, button, section):
        self.stack.set_visible_child_name(section)