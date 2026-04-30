import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from services.systemd import SERVICES, get_status, start_service, stop_service


class ServiceRow(Gtk.Box):
    def __init__(self, service: dict):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.service_id = service["id"]

        # Nombre del servicio
        label = Gtk.Label(label=service["label"])
        label.set_hexpand(True)
        label.set_xalign(0)
        self.append(label)

        # Indicador de estado
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        # Botón acción
        self.action_button = Gtk.Button()
        self.action_button.connect("clicked", self.on_action_clicked)
        self.append(self.action_button)

        # Cargar estado inicial
        self.refresh()

    def refresh(self):
        active = get_status(self.service_id)
        if active:
            self.status_label.set_markup("<span color='green'>● activo</span>")
            self.action_button.set_label("Parar")
        else:
            self.status_label.set_markup("<span color='red'>● inactivo</span>")
            self.action_button.set_label("Arrancar")

    def on_action_clicked(self, button):
        active = get_status(self.service_id)
        if active:
            stop_service(self.service_id)
        else:
            start_service(self.service_id)
        # Pequeña pausa para que systemd actualice el estado
        GLib.timeout_add(500, self.refresh)


class ServiciosPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        # Título
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Servicios</span>")
        title.set_xalign(0)
        self.append(title)

        # Separador
        self.append(Gtk.Separator())

        # Filas de servicios
        self.rows = []
        for service in SERVICES:
            row = ServiceRow(service)
            self.append(row)
            self.rows.append(row)

        # Botón refrescar
        refresh_btn = Gtk.Button(label="Refrescar")
        refresh_btn.connect("clicked", self.on_refresh)
        refresh_btn.set_halign(Gtk.Align.START)
        self.append(refresh_btn)

    def on_refresh(self, button):
        for row in self.rows:
            row.refresh()