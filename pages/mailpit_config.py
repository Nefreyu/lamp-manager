import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from config import settings
from services.systemd import SERVICES, is_installed, install_mailpit_service, get_status


def _spin(min_val: int, max_val: int, value: int) -> Gtk.SpinButton:
    adj = Gtk.Adjustment(value=value, lower=min_val, upper=max_val, step_increment=1, page_increment=10)
    spin = Gtk.SpinButton(adjustment=adj)
    spin.set_numeric(True)
    spin.set_snap_to_ticks(True)
    return spin


def _setting_row(label_text: str, subtitle: str, widget: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    label_box.set_hexpand(True)
    label = Gtk.Label(label=label_text)
    label.set_xalign(0)
    label_box.append(label)
    if subtitle:
        sub = Gtk.Label()
        sub.set_markup(f"<span color='gray' size='small'>{subtitle}</span>")
        sub.set_xalign(0)
        label_box.append(sub)
    row.append(label_box)
    row.append(widget)
    return row


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
        self.storage_switch = Gtk.Switch()
        self.storage_switch.set_active(settings.get("mailpit", "storage_enabled") == "true")
        self.append(_setting_row("Persistencia de mensajes", "Guarda los emails entre reinicios", self.storage_switch))

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

        self.append(Gtk.Separator())

        # Puerto SMTP
        self.smtp_spin = _spin(1, 65535, int(settings.get("mailpit", "smtp_port")))
        self.append(_setting_row("Puerto SMTP", "Por defecto 1025. Cambia si otra app usa ese puerto.", self.smtp_spin))

        # Máximo de mensajes
        self.max_spin = _spin(0, 100000, int(settings.get("mailpit", "max_messages")))
        self.append(_setting_row("Máximo de mensajes", "0 = ilimitado. Por defecto 500.", self.max_spin))

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.append(self.status_label)

        # Conectar señales después de establecer valores iniciales
        self.storage_switch.connect("notify::active", self.on_storage_toggled)
        self.path_entry.connect("activate", lambda _: self._apply_changes())

        path_focus = Gtk.EventControllerFocus()
        path_focus.connect("leave", lambda _: self._apply_changes())
        self.path_entry.add_controller(path_focus)

        self.smtp_spin.connect("value-changed", self._on_spin_changed)
        self.max_spin.connect("value-changed", self._on_spin_changed)

        self._spin_timer = None

    def on_storage_toggled(self, switch, _):
        self.path_entry.set_sensitive(switch.get_active())
        self._apply_changes()

    def _on_spin_changed(self, _):
        if self._spin_timer:
            GLib.source_remove(self._spin_timer)
        self._spin_timer = GLib.timeout_add(800, self._apply_from_timer)

    def _apply_from_timer(self):
        self._spin_timer = None
        self._apply_changes()
        return False

    def _apply_changes(self):
        storage_enabled = self.storage_switch.get_active()
        storage_path = self.path_entry.get_text()
        smtp_port = int(self.smtp_spin.get_value())
        max_messages = int(self.max_spin.get_value())

        settings.set("mailpit", "storage_enabled", str(storage_enabled).lower())
        settings.set("mailpit", "storage_path", storage_path)
        settings.set("mailpit", "smtp_port", str(smtp_port))
        settings.set("mailpit", "max_messages", str(max_messages))

        mailpit = next(s for s in SERVICES if s["id"] == "mailpit")
        if is_installed(mailpit):
            was_running = get_status("mailpit")
            ok = install_mailpit_service(storage_enabled, storage_path, smtp_port, max_messages, start=was_running)
            if ok:
                msg = "Servicio reiniciado correctamente" if was_running else "Configuración actualizada"
                self._show_status(True, msg)
            else:
                self._show_status(False, "Error al aplicar la configuración")

    def _show_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{message}</span>")
        GLib.timeout_add_seconds(3, lambda: self.status_label.set_markup("") or False)
