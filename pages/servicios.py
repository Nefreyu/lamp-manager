import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from services.systemd import (
    SERVICES, get_status, is_installed,
    start_service, stop_service,
    install_mailpit_service, uninstall_mailpit_service
)
from config import settings


class ServiceRow(Gtk.Box):
    def __init__(self, service: dict, navigate_to):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.service = service
        self.service_id = service["id"]
        self.optional = service.get("optional", False)
        self._updating = False

        # Nombre como botón de navegación
        name_btn = Gtk.Button(label=service["label"])
        name_btn.add_css_class("flat")
        name_btn.set_hexpand(True)
        name_btn.get_child().set_xalign(0)
        name_btn.connect("clicked", lambda _: navigate_to(f"service-{self.service_id}"))
        self.append(name_btn)

        # Indicador de estado
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        # Botón instalar/desinstalar (solo servicios opcionales)
        if self.optional:
            self.install_button = Gtk.Button()
            self.install_button.connect("clicked", self.on_install_clicked)
            self.append(self.install_button)

        # Botón abrir en navegador
        self.url = service.get("url")
        if self.url:
            self.link_button = Gtk.Button()
            self.link_button.set_icon_name("web-browser-symbolic")
            self.link_button.set_tooltip_text(self.url)
            self.link_button.set_valign(Gtk.Align.CENTER)
            self.link_button.connect("clicked", self.on_open_url)
            self.append(self.link_button)

        # Switch arrancar/parar
        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        self.switch.connect("state-set", self.on_switch_toggled)
        self.append(self.switch)

        self.refresh()

    def on_open_url(self, button):
        Gio.AppInfo.launch_default_for_uri(self.url, None)

    def refresh(self):
        self._updating = True

        if not is_installed(self.service):
            self.status_label.set_markup("<span color='orange'>⚠ no instalado</span>")
            self.switch.set_active(False)
            self.switch.set_sensitive(False)
            if self.url:
                self.link_button.set_sensitive(False)
            if self.optional:
                self.install_button.set_label("Instalar servicio")
        else:
            active = get_status(self.service_id)
            self.status_label.set_markup("")
            self.switch.set_active(active)
            self.switch.set_sensitive(True)
            if self.url:
                self.link_button.set_sensitive(active)
            if self.optional:
                self.install_button.set_label("Desinstalar servicio")

        self._updating = False

    def on_switch_toggled(self, switch, state):
        if self._updating:
            return False
        if state:
            result = start_service(self.service_id)
        else:
            result = stop_service(self.service_id)
        print(f"Operación en {self.service_id}: {result}")
        GLib.timeout_add(500, self.refresh)
        return False

    def on_install_clicked(self, button):
        if is_installed(self.service):
            uninstall_mailpit_service()
        else:
            storage_enabled = settings.get("mailpit", "storage_enabled") == "true"
            storage_path = settings.get("mailpit", "storage_path")
            install_mailpit_service(storage_enabled, storage_path)
        GLib.timeout_add(500, self.refresh)


class ServiciosPage(Gtk.Box):
    def __init__(self, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Servicios</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        self.rows = []
        for service in SERVICES:
            row = ServiceRow(service, navigate_to)
            self.append(row)
            self.rows.append(row)

        refresh_btn = Gtk.Button(label="Refrescar")
        refresh_btn.connect("clicked", self.on_refresh)
        refresh_btn.set_halign(Gtk.Align.START)
        self.append(refresh_btn)

    def on_refresh(self, button):
        for row in self.rows:
            row.refresh()


class ServiceConfigPage(Gtk.Box):
    def __init__(self, service: dict, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        back_btn = Gtk.Button(label="Servicios")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.set_halign(Gtk.Align.START)
        back_btn.connect("clicked", lambda _: navigate_to("servicios"))
        self.append(back_btn)

        title = Gtk.Label()
        title.set_markup(f"<span size='x-large' weight='bold'>{service['label']}</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        placeholder = Gtk.Label(
            label=f"Sección para la configuración del servicio de {service['label']}"
        )
        placeholder.set_xalign(0)
        self.append(placeholder)
