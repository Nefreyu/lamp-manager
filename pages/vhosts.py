import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib

from config import settings
from services.vhosts import (
    list_projects, vhost_config_path, vhost_is_enabled,
    create_vhost, delete_vhost, enable_vhost, disable_vhost
)


class VHostRow(Gtk.Box):
    def __init__(self, name: str, on_deleted):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.name = name
        self.on_deleted = on_deleted

        label = Gtk.Label(label=name)
        label.set_hexpand(True)
        label.set_xalign(0)
        self.append(label)

        domain_label = Gtk.Label()
        domain_label.set_markup(f"<span color='gray'>{name}.test</span>")
        self.append(domain_label)

        self.link_button = Gtk.Button()
        self.link_button.set_icon_name("web-browser-symbolic")
        self.link_button.set_tooltip_text(f"http://{name}.test")
        self.link_button.set_valign(Gtk.Align.CENTER)
        self.link_button.connect("clicked", self.on_open_url)
        self.append(self.link_button)

        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        self.switch.connect("state-set", self.on_switch_toggled)
        self.append(self.switch)

        delete_btn = Gtk.Button()
        delete_btn.set_icon_name("edit-delete-symbolic")
        delete_btn.set_tooltip_text("Eliminar proyecto")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.add_css_class("destructive-action")
        delete_btn.connect("clicked", self.on_delete_clicked)
        self.append(delete_btn)

        self._refresh()

    def _refresh(self):
        has_config = vhost_config_path(self.name).exists()
        enabled = vhost_is_enabled(self.name)
        self.switch.set_active(enabled)
        self.switch.set_sensitive(has_config)
        self.link_button.set_sensitive(enabled)

    def on_open_url(self, button):
        Gio.AppInfo.launch_default_for_uri(f"http://{self.name}.test", None)

    def on_switch_toggled(self, switch, state):
        if state:
            enable_vhost(self.name)
        else:
            disable_vhost(self.name)
        GLib.timeout_add(500, self._refresh)
        return False

    def on_delete_clicked(self, button):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Eliminar {self.name}?")
        dialog.set_detail(
            f"Se eliminará la configuración de Apache y la entrada en /etc/hosts.\n"
            f"El directorio del proyecto no se borrará."
        )
        dialog.set_buttons(["Cancelar", "Eliminar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, self._on_delete_confirmed)

    def _on_delete_confirmed(self, dialog, result):
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            delete_vhost(self.name)
            self.on_deleted()


class VHostsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Virtual Hosts</span>")
        title.set_hexpand(True)
        title.set_xalign(0)
        header_box.append(title)

        new_btn = Gtk.Button(label="Nuevo proyecto")
        new_btn.set_icon_name("list-add-symbolic")
        new_btn.add_css_class("suggested-action")
        new_btn.connect("clicked", self.on_new_project)
        header_box.append(new_btn)

        self.append(header_box)
        self.append(Gtk.Separator())

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.list_box)

        self._load_projects()

    def _load_projects(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        projects_dir = settings.get("general", "projects_dir")
        projects = list_projects(projects_dir)

        if not projects:
            empty_label = Gtk.Label(label="No hay proyectos en el directorio configurado.")
            empty_label.set_xalign(0)
            self.list_box.append(empty_label)
            return

        for name in projects:
            row = VHostRow(name, on_deleted=self._load_projects)
            self.list_box.append(row)

    def on_new_project(self, button):
        dialog = Gtk.Dialog(title="Nuevo proyecto", transient_for=self.get_root(), modal=True)
        dialog.set_default_size(320, -1)

        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        label = Gtk.Label(label="Nombre del proyecto:")
        label.set_xalign(0)
        content.append(label)

        entry = Gtk.Entry()
        entry.set_placeholder_text("mi-proyecto")
        content.append(entry)

        info = Gtk.Label()
        projects_dir = settings.get("general", "projects_dir")
        info.set_markup(f"<span color='gray' size='small'>Se creará en {projects_dir}</span>")
        info.set_xalign(0)
        content.append(info)

        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Crear", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        entry.connect("activate", lambda e: dialog.response(Gtk.ResponseType.OK))

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                name = entry.get_text().strip()
                if name:
                    create_vhost(name, projects_dir)
                    GLib.timeout_add(500, self._load_projects)
            d.destroy()

        dialog.connect("response", on_response)
        dialog.present()
