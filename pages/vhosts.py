import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio, GLib, Gdk

from config import settings
import threading
from services.vhosts import (
    list_projects, vhost_config_path, vhost_is_enabled,
    create_vhost, enable_vhost, disable_vhost,
    is_mkcert_installed, vhost_has_https, enable_https, disable_https,
    FRAMEWORKS, is_command_installed, scaffold_project,
    trash_vhost, slugify,
)


class VHostRow(Gtk.Box):
    def __init__(self, name: str, on_deleted, on_status, on_configure):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.add_css_class("item-row")
        self.name = name
        self.on_deleted = on_deleted
        self.on_status = on_status
        self._updating = False

        name_btn = Gtk.Button()
        name_btn.add_css_class("flat")
        name_btn.set_hexpand(True)
        name_btn.connect("clicked", lambda _: on_configure(name))
        btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        btn_content.append(name_label)
        domain_label = Gtk.Label()
        domain_label.set_markup(f"<span color='gray'>{name}.test</span>")
        btn_content.append(domain_label)
        name_btn.set_child(btn_content)
        self.append(name_btn)

        self.link_button = Gtk.Button()
        self.link_button.set_icon_name("web-browser-symbolic")
        self.link_button.set_tooltip_text(f"http://{name}.test")
        self.link_button.set_valign(Gtk.Align.CENTER)
        self.link_button.connect("clicked", self.on_open_url)
        self.append(self.link_button)

        folder_btn = Gtk.Button()
        folder_btn.set_icon_name("folder-symbolic")
        folder_btn.set_tooltip_text("Abrir carpeta del proyecto")
        folder_btn.set_valign(Gtk.Align.CENTER)
        folder_btn.connect("clicked", self.on_open_folder)
        self.append(folder_btn)

        self.https_button = Gtk.Button()
        self.https_button.set_valign(Gtk.Align.CENTER)
        self.https_button.set_tooltip_text("Activar/desactivar HTTPS")
        self.https_button.connect("clicked", self.on_https_clicked)
        self.append(self.https_button)

        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        self.switch.connect("state-set", self.on_switch_toggled)
        self.append(self.switch)

        self.delete_btn = Gtk.Button()
        self.delete_btn.set_icon_name("edit-delete-symbolic")
        self.delete_btn.set_tooltip_text("Eliminar proyecto")
        self.delete_btn.set_valign(Gtk.Align.CENTER)
        self.delete_btn.add_css_class("destructive-action")
        self.delete_btn.connect("clicked", self.on_delete_clicked)
        self.append(self.delete_btn)

        self._refresh()

    def _refresh(self):
        self._updating = True
        has_config = vhost_config_path(self.name).exists()
        enabled = vhost_is_enabled(self.name)
        has_https = vhost_has_https(self.name)
        self.switch.set_active(enabled)
        self.switch.set_sensitive(True)
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

    def on_open_folder(self, button):
        projects_dir = settings.get("general", "projects_dir")
        folder = Gio.File.new_for_path(f"{projects_dir}/{self.name}")
        Gio.AppInfo.launch_default_for_uri(folder.get_uri(), None)

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

        if vhost_has_https(self.name):
            disable_https(self.name)
        else:
            enable_https(self.name)
        GLib.timeout_add(500, self._refresh)

    def on_switch_toggled(self, switch, state):
        if self._updating:
            return False
        if state:
            has_config = vhost_config_path(self.name).exists()
            if not has_config:
                projects_dir = settings.get("general", "projects_dir")
                ok = create_vhost(self.name, projects_dir)
            else:
                ok = enable_vhost(self.name)
        else:
            ok = disable_vhost(self.name)
        if not ok:
            self.on_status(False, f"Error al {'activar' if state else 'desactivar'} {self.name}.test")
        GLib.timeout_add(500, self._refresh)
        return False

    def on_delete_clicked(self, button):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Mover {self.name} a la papelera?")
        dialog.set_detail(
            f"La configuración de Apache, los archivos y la base de datos "
            f"se moverán a la papelera. Podrás restaurarlos desde la sección Papelera."
        )
        dialog.set_buttons(["Cancelar", "Mover a la papelera"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, self._on_trash_confirmed)

    def _on_trash_confirmed(self, dialog, result):
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            self.switch.set_sensitive(False)
            self.link_button.set_sensitive(False)
            self.https_button.set_sensitive(False)
            self.delete_btn.set_sensitive(False)

            def run():
                ok = trash_vhost(self.name)
                if ok:
                    GLib.idle_add(self.on_deleted)
                else:
                    GLib.idle_add(self._after_trash_error)

            threading.Thread(target=run, daemon=True).start()

    def _after_trash_error(self):
        self.switch.set_sensitive(True)
        self.https_button.set_sensitive(True)
        self.delete_btn.set_sensitive(True)
        self._refresh()
        self.on_status(False, f"Error al mover {self.name} a la papelera")


class VHostsPage(Gtk.Box):
    def __init__(self, navigate_to_vhost_config, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._navigate_to_vhost_config = navigate_to_vhost_config
        self._navigate_to = navigate_to
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

        trash_btn = Gtk.Button()
        trash_btn.set_icon_name("user-trash-symbolic")
        trash_btn.set_tooltip_text("Papelera")
        trash_btn.connect("clicked", lambda _: self._navigate_to("vhost-trash"))
        header_box.append(trash_btn)

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

    def refresh(self):
        self._load_projects()

    def _load_projects(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        projects = list_projects()

        if not projects:
            empty_label = Gtk.Label(label="No hay proyectos en el directorio configurado.")
            empty_label.set_xalign(0)
            self.list_box.append(empty_label)
            return

        for name in projects:
            row = VHostRow(name, on_deleted=self._load_projects, on_status=self._set_status, on_configure=self._navigate_to_vhost_config)
            self.list_box.append(row)

    def on_new_project(self, button):
        projects_dir = settings.get("general", "projects_dir")

        dialog = Gtk.Dialog(title="Nuevo proyecto", transient_for=self.get_root(), modal=True)
        dialog.set_default_size(360, -1)

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
        entry.set_placeholder_text("Mi Proyecto")
        content.append(entry)

        slug_label = Gtk.Label()
        slug_label.set_xalign(0)
        content.append(slug_label)

        fw_label = Gtk.Label(label="Framework:")
        fw_label.set_xalign(0)
        content.append(fw_label)

        fw_model = Gtk.StringList()
        for fw in FRAMEWORKS:
            fw_model.append(fw["label"])
        fw_dropdown = Gtk.DropDown(model=fw_model)
        fw_dropdown.set_selected(0)
        content.append(fw_dropdown)

        fw_desc = Gtk.Label()
        fw_desc.set_markup(f"<span color='gray' size='small'>{FRAMEWORKS[0]['description']}</span>")
        fw_desc.set_xalign(0)
        content.append(fw_desc)

        warn_label = Gtk.Label(label="")
        warn_label.set_xalign(0)
        content.append(warn_label)

        info = Gtk.Label()
        info.set_markup(f"<span color='gray' size='small'>Se creará en {projects_dir}</span>")
        info.set_xalign(0)
        content.append(info)

        error_label = Gtk.Label(label="")
        error_label.set_xalign(0)
        content.append(error_label)

        progress_label = Gtk.Label(label="")
        progress_label.set_xalign(0)
        content.append(progress_label)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _: dialog.response(Gtk.ResponseType.CANCEL))
        btn_box.append(cancel_btn)

        create_btn = Gtk.Button(label="Crear")
        create_btn.add_css_class("suggested-action")
        create_btn.set_sensitive(False)
        create_btn.connect("clicked", lambda _: dialog.response(Gtk.ResponseType.OK))
        btn_box.append(create_btn)

        content.append(btn_box)

        def _fw_requires_ok():
            fw = FRAMEWORKS[fw_dropdown.get_selected()]
            return not fw.get("requires") or is_command_installed(fw["requires"])

        def _update_create_btn(slug):
            create_btn.set_sensitive(bool(slug) and not vhost_config_path(slug).exists() and _fw_requires_ok())

        def on_name_changed(e):
            slug = slugify(e.get_text())
            if not e.get_text().strip():
                slug_label.set_markup("")
                error_label.set_markup("")
            elif not slug:
                slug_label.set_markup("")
                error_label.set_markup("<span color='red'>El nombre no contiene caracteres válidos.</span>")
            elif vhost_config_path(slug).exists():
                slug_label.set_markup(f"<span color='gray' size='small'>→ {slug}.test</span>")
                error_label.set_markup(f"<span color='red'>Ya existe un proyecto llamado '{slug}'.</span>")
            else:
                slug_label.set_markup(f"<span color='gray' size='small'>→ {slug}.test</span>")
                error_label.set_markup("")
            _update_create_btn(slug)

        def on_framework_changed(dropdown, _):
            fw = FRAMEWORKS[dropdown.get_selected()]
            fw_desc.set_markup(f"<span color='gray' size='small'>{fw['description']}</span>")
            if fw.get("requires") and not is_command_installed(fw["requires"]):
                warn_label.set_markup(
                    f"<span color='orange'>⚠ {fw['requires']} no está instalado</span>"
                )
                create_btn.set_sensitive(False)
            else:
                warn_label.set_markup("")
                _update_create_btn(slugify(entry.get_text()))

        fw_dropdown.connect("notify::selected", on_framework_changed)
        entry.connect("changed", on_name_changed)
        entry.connect("activate", lambda e: dialog.response(Gtk.ResponseType.OK))

        def on_response(d, response):
            if response != Gtk.ResponseType.OK:
                d.destroy()
                return

            name = slugify(entry.get_text())
            if not name:
                error_label.set_markup("<span color='red'>El nombre no contiene caracteres válidos.</span>")
                return
            if vhost_config_path(name).exists():
                error_label.set_markup(f"<span color='red'>Ya existe un proyecto llamado '{name}'.</span>")
                return

            fw = FRAMEWORKS[fw_dropdown.get_selected()]
            create_btn.set_sensitive(False)
            create_btn.set_label("Creando…")
            error_label.set_markup("")

            def run():
                def on_progress(msg):
                    GLib.idle_add(progress_label.set_markup,
                                  f"<span color='gray' size='small'>{msg}</span>")
                ok, err = scaffold_project(fw, name, projects_dir, on_progress)
                if not ok:
                    GLib.idle_add(error_label.set_markup,
                                  f"<span color='red'>Error: {err}</span>")
                    GLib.idle_add(create_btn.set_sensitive, True)
                    GLib.idle_add(create_btn.set_label, "Crear")
                    return

                def finish():
                    ok = create_vhost(name, projects_dir)
                    if ok:
                        self._set_status(True, f"Proyecto {name}.test creado correctamente.")
                        GLib.timeout_add(500, self._load_projects)
                        d.destroy()
                    else:
                        create_btn.set_sensitive(True)
                        create_btn.set_label("Crear")
                        error_label.set_markup(
                            "<span color='red'>Error al crear el vhost. "
                            "Comprueba los permisos sudo y que Apache está instalado.</span>"
                        )
                GLib.idle_add(finish)

            threading.Thread(target=run, daemon=True).start()

        dialog.connect("response", on_response)
        dialog.present()
