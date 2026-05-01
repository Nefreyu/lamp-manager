import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from services.systemd import (
    SERVICES, get_status, service_exists,
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

        # Nombre
        label = Gtk.Label(label=service["label"])
        label.set_hexpand(True)
        label.set_xalign(0)
        self.append(label)

        # Indicador de estado
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        # Botón acción principal (arrancar/parar)
        self.action_button = Gtk.Button()
        self.action_button.connect("clicked", self.on_action_clicked)
        self.append(self.action_button)

        # Botón instalar/desinstalar (solo servicios opcionales)
        if self.optional:
            self.install_button = Gtk.Button()
            self.install_button.connect("clicked", self.on_install_clicked)
            self.append(self.install_button)

        self.refresh()

    def refresh(self):
        if self.optional and not service_exists(self.service_id):
            self.status_label.set_markup("<span color='orange'>⚠ no instalado</span>")
            self.action_button.set_label("-")
            self.action_button.set_sensitive(False)
            self.install_button.set_label("Instalar servicio")
        else:
            active = get_status(self.service_id)
            if active:
                self.status_label.set_markup("<span color='green'>● activo</span>")
                self.action_button.set_label("Parar")
            else:
                self.status_label.set_markup("<span color='red'>● inactivo</span>")
                self.action_button.set_label("Arrancar")
            self.action_button.set_sensitive(True)

            if self.optional:
                self.install_button.set_label("Desinstalar servicio")

    def on_action_clicked(self, button):
        active = get_status(self.service_id)
        print(f"Estado actual de {self.service_id}: {active}")
        if active:
            result = stop_service(self.service_id)
        else:
            result = start_service(self.service_id)
        print(f"Resultado de la operación: {result}")
        GLib.timeout_add(500, self.refresh)

    def on_install_clicked(self, button):
        if service_exists(self.service_id):
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