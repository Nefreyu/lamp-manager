import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from services.systemd import (
    SERVICES, get_status, is_installed,
    start_service, stop_service,
    install_mailpit_service, uninstall_mailpit_service
)
from config import settings

class ServiceRow(Gtk.Box):
    def __init__(self, service: dict):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.service = service
        self.service_id = service["id"]
        self.optional = service.get("optional", False)
        self._updating = False

        # Nombre
        label = Gtk.Label(label=service["label"])
        label.set_hexpand(True)
        label.set_xalign(0)
        self.append(label)

        # Indicador de estado (solo para opcionales no instalados)
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        # Botón instalar/desinstalar (solo servicios opcionales)
        if self.optional:
            self.install_button = Gtk.Button()
            self.install_button.connect("clicked", self.on_install_clicked)
            self.append(self.install_button)

        # Botón abrir en navegador (izquierda del switch)
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
        from gi.repository import Gio
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
            return False  # Ignoramos cambios programáticos

        if state:
            result = start_service(self.service_id)
        else:
            result = stop_service(self.service_id)

        print(f"Operación en {self.service_id}: {result}")
        GLib.timeout_add(500, self.refresh)
        return False  # Dejamos que GTK actualice el estado visualmente

    def on_install_clicked(self, button):
        if is_installed(self.service):
            uninstall_mailpit_service()
        else:
            storage_enabled = settings.get("mailpit", "storage_enabled") == "true"
            storage_path = settings.get("mailpit", "storage_path")
            install_mailpit_service(storage_enabled, storage_path)
        GLib.timeout_add(500, self.refresh)


class ServiciosPage(Gtk.Box):
    def __init__(self):
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
            row = ServiceRow(service)
            self.append(row)
            self.rows.append(row)

        refresh_btn = Gtk.Button(label="Refrescar")
        refresh_btn.connect("clicked", self.on_refresh)
        refresh_btn.set_halign(Gtk.Align.START)
        self.append(refresh_btn)

    def on_refresh(self, button):
        for row in self.rows:
            row.refresh()