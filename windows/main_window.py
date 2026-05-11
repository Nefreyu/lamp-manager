import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Gio, Adw

from pages.servicios import ServiciosPage, ServiceConfigPage
from pages.mailpit_config import MailpitConfigPage
from pages.apache_config import ApacheConfigPage
from pages.mysql_config import MysqlConfigPage
from pages.php_config import PhpConfigPage
from pages.phpmyadmin_config import PhpMyAdminConfigPage
from pages.vhosts import VHostsPage
from pages.vhost_config import VHostConfigPage
from windows.password_dialog import PasswordDialog
from services.systemd import SERVICES, set_password, validate_password
from pages.ajustes import AjustesPage


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_default_size(960, 600)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title = Gtk.Label(label="LAMP Manager")
        header.set_title_widget(title)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)

        menu = Gio.Menu()
        menu.append("Acerca de LAMP Manager", "win.about")
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)
        header.pack_start(menu_btn)

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

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        sidebar.append(Gtk.Separator())

        btn_ajustes = Gtk.Button(label="Ajustes")
        btn_ajustes.connect("clicked", self.on_section_changed, "ajustes")
        sidebar.append(btn_ajustes)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(separator)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_hexpand(True)
        main_box.append(self.stack)

        self.servicios_page = ServiciosPage(self.navigate_to)
        self.stack.add_named(self.servicios_page, "servicios")
        self.stack.add_named(VHostsPage(self.navigate_to_vhost_config), "vhosts")
        self.stack.add_named(AjustesPage(), "ajustes")
        self.vhost_config_page = VHostConfigPage(self.navigate_to)
        self.stack.add_named(self.vhost_config_page, "vhost-config")

        config_pages = {
            "mailpit": MailpitConfigPage,
            "apache2": ApacheConfigPage,
            "mysql": MysqlConfigPage,
            "phpmyadmin": PhpMyAdminConfigPage,
        }
        for service in SERVICES:
            if service["id"].endswith("-fpm"):
                page_class = PhpConfigPage
            else:
                page_class = config_pages.get(service["id"], ServiceConfigPage)
            page = page_class(service, self.navigate_to)
            self.stack.add_named(page, f"service-{service['id']}")

    def navigate_to_vhost_config(self, name: str):
        self.vhost_config_page.load(name)
        self.navigate_to("vhost-config")

    def navigate_to(self, name: str):
        current = self.stack.get_visible_child_name()
        if name == "ajustes":
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP)
        elif current == "ajustes":
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_DOWN)
        else:
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_visible_child_name(name)
        if name == "servicios":
            GLib.idle_add(self.servicios_page.on_refresh, None)

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
        self.navigate_to(section)

    def on_about(self, action, param):
        from config.version import __version__
        dialog = Adw.AboutDialog()
        dialog.set_application_name("LAMP Manager")
        dialog.set_version(__version__)
        dialog.set_developers(["Juan Diez"])
        dialog.set_application_icon("io.github.nefreyu.LampManager")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.present(self)
