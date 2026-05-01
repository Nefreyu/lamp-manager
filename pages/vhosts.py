import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio, GLib, Gdk

from config import settings
from services.vhosts import (
    list_projects, vhost_config_path, vhost_is_enabled,
    create_vhost, delete_vhost, enable_vhost, disable_vhost,
    is_mkcert_installed, vhost_has_https, enable_https, disable_https
)


class VHostRow(Gtk.Box):
    def __init__(self, name: str, on_deleted, on_status):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.name = name
        self.on_deleted = on_deleted
        self.on_status = on_status
        self._updating = False

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

        self.https_button = Gtk.Button()
        self.https_button.set_valign(Gtk.Align.CENTER)
        self.https_button.set_tooltip_text("Activar/desactivar HTTPS")
        self.https_button.connect("clicked", self.on_https_clicked)
        self.append(self.https_button)

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
        self._updating = True
        has_config = vhost_config_path(self.name).exists()
        enabled = vhost_is_enabled(self.name)
        has_https = vhost_has_https(self.name)
        self.switch.set_active(enabled)
        self.switch.set_sensitive(has_config)
        self.link_button.set_sensitive(enabled)
        self.link_button.set_tooltip_text(
            f"https://{self.name}.test" if has_https else f"http://{self.name}.test"
        )
        self.https_button.set_icon_name(
            "changes-prevent-symbolic" if has_https else "changes-allow-symbolic"
        )
        self.https_button.set_tooltip_text(
            "HTTPS activo — pulsa para desactivar" if has_https else "Activar HTTPS"
        )
        if has_https:
            self.https_button.add_css_class("https-active")
        else:
            self.https_button.remove_css_class("https-active")
        self._updating = False

    def on_open_url(self, button):
        protocol = "https" if vhost_has_https(self.name) else "http"
        Gio.AppInfo.launch_default_for_uri(f"{protocol}://{self.name}.test", None)

    def on_https_clicked(self, button):
        if not is_mkcert_installed():
            dialog = Gtk.AlertDialog()
            dialog.set_message("mkcert no está instalado")
            dialog.set_detail(
                "Para activar HTTPS necesitas instalar mkcert:\n\n"
                "sudo apt install mkcert"
            )
            dialog.set_buttons(["Aceptar"])
            dialog.show(self.get_root())
            return

        projects_dir = settings.get("general", "projects_dir")
        if vhost_has_https(self.name):
            disable_https(self.name, projects_dir)
        else:
            enable_https(self.name, projects_dir)
        GLib.timeout_add(500, self._refresh)

    def on_switch_toggled(self, switch, state):
        if self._updating:
            return False
        if state:
            ok = enable_vhost(self.name)
        else:
            ok = disable_vhost(self.name)
        if not ok:
            self.on_status(False, f"Error al {'activar' if state else 'desactivar'} {self.name}.test")
        GLib.timeout_add(500, self._refresh)
        return False

    def on_delete_clicked(self, button):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Eliminar {self.name}?")
        projects_dir = settings.get("general", "projects_dir")
        dialog.set_detail(
            f"Se eliminarán la configuración de Apache, la entrada en /etc/hosts "
            f"y el directorio {projects_dir}/{self.name}.\n\n"
            f"Esta acción no se puede deshacer."
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
            projects_dir = settings.get("general", "projects_dir")
            ok = delete_vhost(self.name, projects_dir)
            if ok:
                self.on_deleted()
            else:
                self.on_status(False, f"Error al eliminar {self.name}: comprueba los permisos sudo")


class VHostsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"button.https-active { color: #26a269; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

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

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.append(self.status_label)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.list_box)

        self._load_projects()

    def _set_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{message}</span>")
        if success:
            GLib.timeout_add_seconds(15, lambda: self.status_label.set_markup("") or False)

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
            row = VHostRow(name, on_deleted=self._load_projects, on_status=self._set_status)
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

        name_label = Gtk.Label(label="Nombre del proyecto:")
        name_label.set_xalign(0)
        content.append(name_label)

        entry = Gtk.Entry()
        entry.set_placeholder_text("mi-proyecto")
        content.append(entry)

        projects_dir = settings.get("general", "projects_dir")
        info = Gtk.Label()
        info.set_markup(f"<span color='gray' size='small'>Se creará en {projects_dir}</span>")
        info.set_xalign(0)
        content.append(info)

        error_label = Gtk.Label(label="")
        error_label.set_xalign(0)
        content.append(error_label)

        create_btn = dialog.add_button("Crear", Gtk.ResponseType.OK)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.set_default_response(Gtk.ResponseType.OK)

        entry.connect("activate", lambda e: dialog.response(Gtk.ResponseType.OK))

        def on_response(d, response):
            if response != Gtk.ResponseType.OK:
                d.destroy()
                return

            name = entry.get_text().strip()
            if not name:
                error_label.set_markup("<span color='red'>El nombre no puede estar vacío.</span>")
                return

            create_btn.set_sensitive(False)
            create_btn.set_label("Creando…")

            ok = create_vhost(name, projects_dir)
            if ok:
                self._set_status(True, f"Proyecto {name}.test creado correctamente.")
                GLib.timeout_add(500, self._load_projects)
                d.destroy()
            else:
                create_btn.set_sensitive(True)
                create_btn.set_label("Crear")
                error_label.set_markup(
                    "<span color='red'>Error al crear el proyecto.\n"
                    "Comprueba que la contraseña sudo es correcta y que Apache está instalado.</span>"
                )

        dialog.connect("response", on_response)
        dialog.present()
