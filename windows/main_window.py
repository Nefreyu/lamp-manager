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
from pages.vhost_trash import VHostTrashPage
from windows.password_dialog import PasswordDialog
from services.systemd import SERVICES, set_password, validate_password
from services.keyring import get_sudo_password, save_sudo_password
from pages.ajustes import AjustesPage

NAV_ITEMS = [
    ("Servicios",     "servicios", "computer-symbolic"),
    ("Virtual Hosts", "vhosts",    "network-server-symbolic"),
]
SETTINGS_ITEMS = [
    ("Ajustes", "ajustes", "preferences-system-symbolic"),
]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_default_size(960, 600)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_content(main_box)

        # ── SIDEBAR ──────────────────────────────────────────────────
        sidebar_view = Adw.ToolbarView()
        sidebar_view.set_size_request(200, -1)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_header.set_title_widget(Gtk.Box())

        self.search_toggle = Gtk.ToggleButton()
        self.search_toggle.set_icon_name("system-search-symbolic")
        self.search_toggle.set_tooltip_text("Buscar")
        sidebar_header.pack_start(self.search_toggle)

        menu = Gio.Menu()
        menu.append("Acerca de LAMP Manager", "win.about")
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)
        sidebar_header.pack_end(menu_btn)
        sidebar_view.add_top_bar(sidebar_header)

        search_bar = Gtk.SearchBar()
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Buscar…")
        search_bar.set_child(self.search_entry)
        self.search_toggle.connect(
            "toggled", lambda btn: search_bar.set_search_mode(btn.get_active())
        )
        self.search_entry.connect("search-changed", self._on_search_changed)
        sidebar_view.add_top_bar(search_bar)

        self._nav_rows = {}

        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_vexpand(True)
        self.nav_list.set_filter_func(self._filter_row)
        self.nav_list.connect("row-selected", self._on_nav_selected)

        for label, section, icon in NAV_ITEMS:
            row = self._make_nav_row(label, section, icon)
            self.nav_list.append(row)
            self._nav_rows[section] = row

        self.settings_list = Gtk.ListBox()
        self.settings_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.settings_list.add_css_class("navigation-sidebar")
        self.settings_list.set_filter_func(self._filter_row)
        self.settings_list.connect("row-selected", self._on_nav_selected)

        for label, section, icon in SETTINGS_ITEMS:
            row = self._make_nav_row(label, section, icon)
            self.settings_list.append(row)
            self._nav_rows[section] = row

        sidebar_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_content.append(self.nav_list)
        sidebar_content.append(Gtk.Separator())
        sidebar_content.append(self.settings_list)
        sidebar_view.set_content(sidebar_content)

        main_box.append(sidebar_view)
        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # ── CONTENT ──────────────────────────────────────────────────
        content_view = Adw.ToolbarView()
        content_view.set_hexpand(True)

        content_header = Adw.HeaderBar()
        content_header.set_show_start_title_buttons(False)
        content_header.set_title_widget(Gtk.Label(label="LAMP Manager"))
        content_view.add_top_bar(content_header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_hexpand(True)
        content_view.set_content(self.stack)
        main_box.append(content_view)

        # ── PAGES ────────────────────────────────────────────────────
        self.servicios_page = ServiciosPage(self.navigate_to)
        self.stack.add_named(self.servicios_page, "servicios")
        self.vhosts_page = VHostsPage(self.navigate_to_vhost_config, self.navigate_to)
        self.stack.add_named(self.vhosts_page, "vhosts")
        self.vhost_trash_page = VHostTrashPage(self.navigate_to)
        self.stack.add_named(self.vhost_trash_page, "vhost-trash")
        self.stack.add_named(AjustesPage(), "ajustes")
        self.vhost_config_page = VHostConfigPage(self.navigate_to)
        self.stack.add_named(self.vhost_config_page, "vhost-config")

        config_pages = {
            "mailpit":    MailpitConfigPage,
            "apache2":    ApacheConfigPage,
            "mysql":      MysqlConfigPage,
            "phpmyadmin": PhpMyAdminConfigPage,
        }
        for service in SERVICES:
            page_class = PhpConfigPage if service["id"].endswith("-fpm") else config_pages.get(service["id"], ServiceConfigPage)
            self.stack.add_named(page_class(service, self.navigate_to), f"service-{service['id']}")

        self.nav_list.select_row(self._nav_rows["servicios"])

    def _make_nav_row(self, label: str, section: str, icon: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._section = section
        row._label_text = label.lower()

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(Gtk.Image.new_from_icon_name(icon))
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        box.append(lbl)
        row.set_child(box)
        return row

    def _filter_row(self, row) -> bool:
        query = self.search_entry.get_text().lower().strip()
        return not query or query in row._label_text

    def _on_search_changed(self, entry):
        self.nav_list.invalidate_filter()
        self.settings_list.invalidate_filter()

    def _on_nav_selected(self, listbox, row):
        if row is None:
            return
        self.navigate_to(row._section)

    def _select_nav_row(self, section):
        row = self._nav_rows.get(section)
        if not row:
            return
        if section == "ajustes":
            self.nav_list.select_row(None)
            self.settings_list.select_row(row)
        else:
            self.settings_list.select_row(None)
            self.nav_list.select_row(row)

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
        if name in self._nav_rows:
            self._select_nav_row(name)
        if name == "servicios":
            GLib.idle_add(self.servicios_page.on_refresh, None)
        elif name == "vhosts":
            GLib.idle_add(self.vhosts_page.refresh)
        elif name == "vhost-trash":
            GLib.idle_add(self.vhost_trash_page.refresh)

    def request_password(self):
        stored = get_sudo_password()
        if stored and validate_password(stored):
            set_password(stored)
            return
        self.dialog = PasswordDialog(self, self.on_password_success, self.on_password_cancel)
        self.dialog.present()

    def on_password_success(self, password):
        if validate_password(password):
            set_password(password)
            save_sudo_password(password)
            self.dialog.close()
        else:
            self.dialog.show_error()

    def on_password_cancel(self):
        self.dialog.close()
        self.close()

    def on_about(self, action, param):
        from config.version import __version__
        dialog = Adw.AboutDialog()
        dialog.set_application_name("LAMP Manager")
        dialog.set_developer_name("Juan Diez")
        dialog.set_version(__version__)
        dialog.set_comments("Una herramienta para gestionar tu entorno de desarrollo LAMP en Linux.")
        dialog.set_developers(["Juan Diez"])
        dialog.set_application_icon("io.github.nefreyu.LampManager")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.present(self)
