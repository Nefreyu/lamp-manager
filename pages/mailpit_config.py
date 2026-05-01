import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from config import settings
from services.systemd import SERVICES, is_installed, uninstall_mailpit_service, install_mailpit_service


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
        self.storage_switch.set_active(
            settings.get("mailpit", "storage_enabled") == "true"
        )
        self.storage_switch.connect("notify::active", self.on_storage_toggled)
        storage_box.append(self.storage_switch)
        self.append(storage_box)

        # Ruta del archivo de base de datos
        path_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        path_label = Gtk.Label(label="Ruta del archivo de base de datos")
        path_label.set_xalign(0)
        path_box.append(path_label)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_text(settings.get("mailpit", "storage_path"))
        self.path_entry.set_sensitive(
            settings.get("mailpit", "storage_enabled") == "true"
        )
        path_box.append(self.path_entry)
        self.append(path_box)

        save_btn = Gtk.Button(label="Guardar")
        save_btn.add_css_class("suggested-action")
        save_btn.set_halign(Gtk.Align.START)
        save_btn.connect("clicked", self.on_save)
        self.append(save_btn)

        self.confirm_label = Gtk.Label(label="")
        self.append(self.confirm_label)

    def on_storage_toggled(self, switch, _):
        self.path_entry.set_sensitive(switch.get_active())

    def on_save(self, button):
        settings.set("mailpit", "storage_enabled", str(self.storage_switch.get_active()).lower())
        settings.set("mailpit", "storage_path", self.path_entry.get_text())

        mailpit = next(s for s in SERVICES if s["id"] == "mailpit")
        if is_installed(mailpit):
            uninstall_mailpit_service()
            install_mailpit_service(self.storage_switch.get_active(), self.path_entry.get_text())
            self.confirm_label.set_markup("<span color='green'>Ajustes guardados y servicio reiniciado correctamente.</span>")
        else:
            self.confirm_label.set_markup("<span color='green'>Ajustes guardados correctamente.</span>")
