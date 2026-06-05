import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from config import settings


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

        save_btn = Gtk.Button(label="Guardar")
        save_btn.add_css_class("suggested-action")
        save_btn.set_halign(Gtk.Align.START)
        save_btn.connect("clicked", self.on_save)
        self.append(save_btn)

        self.confirm_label = Gtk.Label(label="")
        self.append(self.confirm_label)

    def _on_tray_switch(self, switch, state):
        settings.set("general", "minimize_to_tray", "true" if state else "false")
        return False

    def on_save(self, button):
        settings.set("general", "projects_dir", self.projects_entry.get_text())
        self.confirm_label.set_markup("<span color='green'>Ajustes guardados correctamente.</span>")
