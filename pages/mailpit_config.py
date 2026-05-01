import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from config import settings
from services.systemd import SERVICES, is_installed, install_mailpit_service, get_status


class MailpitConfigPage(Gtk.Box):
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

        # Persistencia de mensajes
        storage_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        storage_label = Gtk.Label(label="Persistencia de mensajes")
        storage_label.set_hexpand(True)
        storage_label.set_xalign(0)
        storage_box.append(storage_label)

        self.storage_switch = Gtk.Switch()
        self.storage_switch.set_active(settings.get("mailpit", "storage_enabled") == "true")
        storage_box.append(self.storage_switch)
        self.append(storage_box)

        # Ruta del archivo de base de datos
        path_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        path_label = Gtk.Label(label="Ruta del archivo de base de datos")
        path_label.set_xalign(0)
        path_box.append(path_label)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_text(settings.get("mailpit", "storage_path"))
        self.path_entry.set_sensitive(settings.get("mailpit", "storage_enabled") == "true")
        path_box.append(self.path_entry)
        self.append(path_box)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.append(self.status_label)

        # Conectar señales después de establecer valores iniciales
        self.storage_switch.connect("notify::active", self.on_storage_toggled)
        self.path_entry.connect("activate", lambda _: self._apply_changes())

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", lambda _: self._apply_changes())
        self.path_entry.add_controller(focus_ctrl)

    def on_storage_toggled(self, switch, _):
        self.path_entry.set_sensitive(switch.get_active())
        self._apply_changes()

    def _apply_changes(self):
        storage_enabled = self.storage_switch.get_active()
        storage_path = self.path_entry.get_text()
        settings.set("mailpit", "storage_enabled", str(storage_enabled).lower())
        settings.set("mailpit", "storage_path", storage_path)

        mailpit = next(s for s in SERVICES if s["id"] == "mailpit")
        if is_installed(mailpit):
            was_running = get_status("mailpit")
            ok = install_mailpit_service(storage_enabled, storage_path, start=was_running)
            if ok:
                msg = "Servicio reiniciado correctamente" if was_running else "Configuración actualizada"
                self._show_status(True, msg)
            else:
                self._show_status(False, "Error al aplicar la configuración")

    def _show_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{message}</span>")
        GLib.timeout_add_seconds(3, lambda: self.status_label.set_markup("") or False)
