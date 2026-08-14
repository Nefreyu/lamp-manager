import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

import threading

from config import settings
from services.autostart import is_enabled as autostart_is_enabled, enable as autostart_enable, disable as autostart_disable
import services.apache as apache
import services.nginx as nginx
from services.vhosts import sync_apache, sync_nginx


def _spin(min_val: int, max_val: int, value: int) -> Gtk.SpinButton:
    adj = Gtk.Adjustment(value=value, lower=min_val, upper=max_val, step_increment=1, page_increment=10)
    spin = Gtk.SpinButton(adjustment=adj)
    spin.set_numeric(True)
    spin.set_snap_to_ticks(True)
    return spin


class AjustesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Ajustes</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        general_title = Gtk.Label()
        general_title.set_markup("<span weight='bold'>General</span>")
        general_title.set_xalign(0)
        self.append(general_title)

        projects_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        projects_label = Gtk.Label(label="Directorio de proyectos")
        projects_label.set_xalign(0)
        projects_box.append(projects_label)

        self.projects_entry = Gtk.Entry()
        self.projects_entry.set_text(settings.get("general", "projects_dir"))
        projects_box.append(self.projects_entry)
        self.append(projects_box)

        autostart_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        autostart_label = Gtk.Label(label="Iniciar al arrancar el sistema")
        autostart_label.set_xalign(0)
        autostart_label.set_hexpand(True)
        autostart_row.append(autostart_label)
        self.autostart_switch = Gtk.Switch()
        self.autostart_switch.set_active(autostart_is_enabled())
        self.autostart_switch.set_valign(Gtk.Align.CENTER)
        self.autostart_switch.connect("state-set", self._on_autostart_switch)
        autostart_row.append(self.autostart_switch)
        self.append(autostart_row)

        tray_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tray_label = Gtk.Label(label="Minimizar al área de notificación al cerrar")
        tray_label.set_xalign(0)
        tray_label.set_hexpand(True)
        tray_row.append(tray_label)
        self.tray_switch = Gtk.Switch()
        self.tray_switch.set_active(settings.get("general", "minimize_to_tray") == "true")
        self.tray_switch.set_valign(Gtk.Align.CENTER)
        self.tray_switch.connect("state-set", self._on_tray_switch)
        tray_row.append(self.tray_switch)
        self.append(tray_row)

        self.append(Gtk.Separator())

        ports_title = Gtk.Label()
        ports_title.set_markup("<span weight='bold'>Puertos</span>")
        ports_title.set_xalign(0)
        self.append(ports_title)

        ports_subtitle = Gtk.Label()
        ports_subtitle.set_markup(
            "<span color='gray' size='small'>Puertos usados por Apache y Nginx para servir "
            "los proyectos .test. Al guardar se regeneran los vhosts existentes.</span>"
        )
        ports_subtitle.set_xalign(0)
        self.append(ports_subtitle)

        apache_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self.apache_http_spin = _spin(1, 65535, apache.get_http_port())
        apache_row.append(self._port_field("Apache — puerto HTTP", self.apache_http_spin))
        self.apache_https_spin = _spin(1, 65535, apache.get_https_port())
        apache_row.append(self._port_field("Apache — puerto HTTPS", self.apache_https_spin))
        self.append(apache_row)

        nginx_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self.nginx_http_spin = _spin(1, 65535, nginx.get_http_port())
        nginx_row.append(self._port_field("Nginx — puerto HTTP", self.nginx_http_spin))
        self.nginx_https_spin = _spin(1, 65535, nginx.get_https_port())
        nginx_row.append(self._port_field("Nginx — puerto HTTPS", self.nginx_https_spin))
        self.append(nginx_row)

        save_btn = Gtk.Button(label="Guardar")
        save_btn.add_css_class("suggested-action")
        save_btn.set_halign(Gtk.Align.START)
        save_btn.connect("clicked", self.on_save)
        self.append(save_btn)

        self.confirm_label = Gtk.Label(label="")
        self.append(self.confirm_label)

    def _on_autostart_switch(self, switch, state):
        if state:
            autostart_enable()
        else:
            autostart_disable()
        return False

    def _on_tray_switch(self, switch, state):
        settings.set("general", "minimize_to_tray", "true" if state else "false")
        return False

    def _port_field(self, label_text: str, spin: Gtk.SpinButton) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_hexpand(True)
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        box.append(label)
        box.append(spin)
        return box

    def _set_port_spins_sensitive(self, sensitive: bool):
        for spin in (self.apache_http_spin, self.apache_https_spin,
                     self.nginx_http_spin, self.nginx_https_spin):
            spin.set_sensitive(sensitive)

    def on_save(self, button):
        settings.set("general", "projects_dir", self.projects_entry.get_text())

        ports = [
            ("apache", "http_port", int(self.apache_http_spin.get_value())),
            ("apache", "https_port", int(self.apache_https_spin.get_value())),
            ("nginx", "http_port", int(self.nginx_http_spin.get_value())),
            ("nginx", "https_port", int(self.nginx_https_spin.get_value())),
        ]
        values = [value for _, _, value in ports]
        if len(set(values)) != len(values):
            self.confirm_label.set_markup(
                "<span color='red'>Los puertos de Apache y Nginx deben ser distintos entre sí.</span>"
            )
            return

        if not any(str(value) != settings.get(section, key) for section, key, value in ports):
            self.confirm_label.set_markup("<span color='green'>Ajustes guardados correctamente.</span>")
            return

        for section, key, value in ports:
            settings.set(section, key, str(value))

        button.set_sensitive(False)
        self._set_port_spins_sensitive(False)
        self.confirm_label.set_markup("<span color='gray'>Aplicando cambios de puertos…</span>")

        def run():
            ok = sync_apache()
            ok = sync_nginx() and ok
            GLib.idle_add(self._after_ports_saved, button, ok)

        threading.Thread(target=run, daemon=True).start()

    def _after_ports_saved(self, button, ok: bool):
        button.set_sensitive(True)
        self._set_port_spins_sensitive(True)
        if ok:
            self.confirm_label.set_markup(
                "<span color='green'>Ajustes guardados y puertos aplicados correctamente.</span>"
            )
        else:
            self.confirm_label.set_markup(
                "<span color='red'>Puertos guardados, pero hubo errores al aplicar la configuración.</span>"
            )
        return False
