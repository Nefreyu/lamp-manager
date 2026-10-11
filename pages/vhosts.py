import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio, GLib, Gdk

from config import settings
import threading
from pathlib import Path
from services.vhosts import (
    list_projects, list_orphan_folders, vhost_config_path, vhost_is_enabled,
    create_vhost, enable_vhost, disable_vhost,
    is_mkcert_installed, vhost_has_https, enable_https, disable_https,
    FRAMEWORKS, is_command_installed, scaffold_project,
    trash_vhost, slugify, get_project_dir, is_valid_vhost_name, register_orphan,
    is_inside_projects_dir, find_vhost_conflict, find_folder_conflict,
)
from services.nginx import get_http_port as get_nginx_http_port, get_https_port as get_nginx_https_port
from services.apache import get_http_port as get_apache_http_port, get_https_port as get_apache_https_port


def _nginx_installed() -> bool:
    return Path("/usr/sbin/nginx").exists()


def _apache_url(name: str, https: bool) -> str:
    protocol = "https" if https else "http"
    port = get_apache_https_port() if https else get_apache_http_port()
    default = 443 if https else 80
    suffix = f":{port}" if port != default else ""
    return f"{protocol}://{name}.test{suffix}"


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
        domain_label.set_markup(f"<span color='gray'>{GLib.markup_escape_text(name)}.test</span>")
        btn_content.append(domain_label)
        projects_dir = settings.get("general", "projects_dir")
        project_dir = get_project_dir(name)
        if project_dir is not None and not is_inside_projects_dir(project_dir, projects_dir):
            outside_label = Gtk.Label()
            outside_label.set_markup(
                f"<span color='orange' size='small'>fuera de "
                f"{GLib.markup_escape_text(projects_dir.replace(str(Path.home()), '~', 1))}</span>"
            )
            outside_label.set_tooltip_text(
                f"El DocumentRoot apunta a {project_dir}, fuera del directorio de proyectos. "
                "Al moverlo a la papelera su carpeta no se moverá."
            )
            btn_content.append(outside_label)
        name_btn.set_child(btn_content)
        self.append(name_btn)

        self.link_button = Gtk.Button()
        self.link_button.set_icon_name("web-browser-symbolic")
        self.link_button.set_tooltip_text(f"http://{name}.test")
        self.link_button.set_valign(Gtk.Align.CENTER)
        self.link_button.connect("clicked", self.on_open_url)
        self.append(self.link_button)

        self.nginx_link_button = None
        if _nginx_installed():
            self.nginx_link_button = Gtk.Button()
            self.nginx_link_button.set_icon_name("web-browser-symbolic")
            self.nginx_link_button.add_css_class("flat")
            self.nginx_link_button.set_valign(Gtk.Align.CENTER)
            self.nginx_link_button.connect("clicked", self.on_open_nginx_url)
            self.append(self.nginx_link_button)

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
        self.link_button.set_tooltip_text(_apache_url(self.name, has_https))
        if self.nginx_link_button:
            port = get_nginx_https_port() if has_https else get_nginx_http_port()
            protocol = "https" if has_https else "http"
            self.nginx_link_button.set_sensitive(enabled)
            self.nginx_link_button.set_tooltip_text(f"{protocol}://{self.name}.test:{port} (Nginx)")
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
        Gio.AppInfo.launch_default_for_uri(_apache_url(self.name, vhost_has_https(self.name)), None)

    def on_open_nginx_url(self, button):
        has_https = vhost_has_https(self.name)
        protocol = "https" if has_https else "http"
        port = get_nginx_https_port() if has_https else get_nginx_http_port()
        Gio.AppInfo.launch_default_for_uri(f"{protocol}://{self.name}.test:{port}", None)

    def on_open_folder(self, button):
        project_dir = get_project_dir(self.name)
        if project_dir is None:
            project_dir = Path(settings.get("general", "projects_dir")) / self.name
        folder = Gio.File.new_for_path(str(project_dir))
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

            projects_dir = settings.get("general", "projects_dir")

            def run():
                ok, warning = trash_vhost(self.name, projects_dir)
                if ok:
                    GLib.idle_add(self._after_trash_ok, warning)
                else:
                    GLib.idle_add(self._after_trash_error)

            threading.Thread(target=run, daemon=True).start()

    def _after_trash_ok(self, warning: str):
        # on_status antes de on_deleted: on_deleted recarga la lista y destruye esta fila
        if warning:
            self.on_status(True, f"{self.name}.test movido a la papelera. {warning}", warning=True)
        self.on_deleted()

    def _after_trash_error(self):
        self.switch.set_sensitive(True)
        self.https_button.set_sensitive(True)
        self.delete_btn.set_sensitive(True)
        self._refresh()
        self.on_status(False, f"Error al mover {self.name} a la papelera")


class OrphanRow(Gtk.Box):
    def __init__(self, name: str, on_registered, on_status):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.add_css_class("item-row")
        self.name = name
        self.on_registered = on_registered
        self.on_status = on_status

        icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        icon.set_valign(Gtk.Align.CENTER)
        self.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        text_box.append(name_label)
        self.append(text_box)

        slug = slugify(name)
        if is_valid_vhost_name(name):
            self._button_label = "Registrar como vhost"
        else:
            hint = Gtk.Label()
            hint.set_xalign(0)
            hint.set_wrap(True)
            if slug:
                hint.set_markup(
                    "<span color='orange' size='small'>El nombre no es válido como dominio; "
                    f"se renombrará a {GLib.markup_escape_text(slug)}</span>"
                )
                self._button_label = f"Renombrar a «{slug}» y registrar"
            else:
                hint.set_markup(
                    "<span color='orange' size='small'>El nombre no es válido como dominio; "
                    "renombra la carpeta para poder registrarla</span>"
                )
                self._button_label = "Registrar como vhost"
            text_box.append(hint)

        self.register_btn = Gtk.Button(label=self._button_label)
        self.register_btn.add_css_class("suggested-action")
        self.register_btn.set_valign(Gtk.Align.CENTER)
        self.register_btn.set_sensitive(bool(slug) or is_valid_vhost_name(name))
        self.register_btn.connect("clicked", self._on_register)
        self.append(self.register_btn)

    def _on_register(self, button):
        button.set_sensitive(False)
        button.set_label("Registrando…")
        projects_dir = settings.get("general", "projects_dir")

        def run():
            result = register_orphan(projects_dir, self.name)
            GLib.idle_add(self._finish, *result)

        threading.Thread(target=run, daemon=True).start()

    def _finish(self, ok: bool, vhost_name: str, error: str):
        if ok:
            self.on_status(True, f"Proyecto {vhost_name}.test registrado correctamente.")
            self.on_registered()
        else:
            self.register_btn.set_sensitive(True)
            self.register_btn.set_label(self._button_label)
            self.on_status(False, error)
            # Si la carpeta llegó a renombrarse, la lista debe reflejarlo
            if vhost_name and vhost_name != self.name:
                self.on_registered()


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
        self.status_label.set_wrap(True)
        self.append(self.status_label)
        self._status_timeout_id: int | None = None

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.list_box)

        self.orphan_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.orphan_section)

        self.connect("map", lambda *_: self._load_projects())
        self._load_projects()

    def _set_status(self, success: bool, message: str, warning: bool = False):
        """Éxito: verde, 15 s. Aviso: naranja, 10 s. Error: rojo, hasta el siguiente mensaje."""
        if warning:
            color, clear_after = "orange", 10
        elif success:
            color, clear_after = "green", 15
        else:
            color, clear_after = "red", None
        self.status_label.set_markup(f"<span color='{color}'>{GLib.markup_escape_text(message)}</span>")
        # Un temporizador pendiente de un mensaje anterior no debe borrar este
        if self._status_timeout_id is not None:
            GLib.source_remove(self._status_timeout_id)
            self._status_timeout_id = None
        if clear_after is not None:
            self._status_timeout_id = GLib.timeout_add_seconds(clear_after, self._clear_status)

    def _clear_status(self) -> bool:
        self.status_label.set_markup("")
        self._status_timeout_id = None
        return False

    def refresh(self):
        self._load_projects()

    def _load_projects(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        while child := self.orphan_section.get_first_child():
            self.orphan_section.remove(child)

        projects = list_projects()

        if not projects:
            empty_label = Gtk.Label(label="No hay proyectos en el directorio configurado.")
            empty_label.set_xalign(0)
            self.list_box.append(empty_label)
        else:
            for name in projects:
                row = VHostRow(name, on_deleted=self._load_projects, on_status=self._set_status, on_configure=self._navigate_to_vhost_config)
                self.list_box.append(row)

        projects_dir = settings.get("general", "projects_dir")
        orphans = list_orphan_folders(projects_dir)
        if orphans:
            sep = Gtk.Separator()
            sep.set_margin_top(12)
            self.orphan_section.append(sep)

            orphan_title = Gtk.Label()
            orphan_title.set_markup("<span weight='bold'>Sitios no registrados</span>")
            orphan_title.set_xalign(0)
            orphan_title.set_margin_top(6)
            self.orphan_section.append(orphan_title)

            orphan_subtitle = Gtk.Label()
            orphan_subtitle.set_markup(
                "<span color='gray' size='small'>"
                "Carpetas detectadas en el directorio de proyectos sin vhost asociado."
                "</span>"
            )
            orphan_subtitle.set_xalign(0)
            self.orphan_section.append(orphan_subtitle)

            for name in orphans:
                row = OrphanRow(name, on_registered=self._load_projects, on_status=self._set_status)
                self.orphan_section.append(row)

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
        fw_desc.set_markup(f"<span color='gray' size='small'>{GLib.markup_escape_text(FRAMEWORKS[0]['description'])}</span>")
        fw_desc.set_xalign(0)
        content.append(fw_desc)

        warn_label = Gtk.Label(label="")
        warn_label.set_xalign(0)
        content.append(warn_label)

        info = Gtk.Label()
        info.set_markup(f"<span color='gray' size='small'>Se creará en {GLib.markup_escape_text(projects_dir)}</span>")
        info.set_xalign(0)
        content.append(info)

        error_label = Gtk.Label(label="")
        error_label.set_xalign(0)
        error_label.set_wrap(True)
        error_label.set_selectable(True)
        content.append(error_label)

        progress_label = Gtk.Label(label="")
        progress_label.set_xalign(0)
        progress_label.set_wrap(True)
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

        def _conflict_message(slug: str) -> str | None:
            existing = find_vhost_conflict(slug)
            if existing:
                return f"Ya existe un proyecto llamado «{existing}»."
            folder = find_folder_conflict(Path(projects_dir), slug)
            if folder:
                return (
                    f"Ya existe la carpeta {folder}. Si es un proyecto, regístralo "
                    "desde «Sitios no registrados»."
                )
            return None

        def _update_create_btn(slug):
            create_btn.set_sensitive(bool(slug) and _conflict_message(slug) is None and _fw_requires_ok())

        def on_name_changed(e):
            slug = slugify(e.get_text())
            conflict = _conflict_message(slug) if slug else None
            if not e.get_text().strip():
                slug_label.set_markup("")
                error_label.set_markup("")
            elif not slug:
                slug_label.set_markup("")
                error_label.set_markup("<span color='red'>El nombre no contiene caracteres válidos.</span>")
            elif conflict:
                slug_label.set_markup(f"<span color='gray' size='small'>→ {slug}.test</span>")
                error_label.set_markup(f"<span color='red'>{GLib.markup_escape_text(conflict)}</span>")
            else:
                slug_label.set_markup(f"<span color='gray' size='small'>→ {slug}.test</span>")
                error_label.set_markup("")
            _update_create_btn(slug)

        def on_framework_changed(dropdown, _):
            fw = FRAMEWORKS[dropdown.get_selected()]
            fw_desc.set_markup(f"<span color='gray' size='small'>{GLib.markup_escape_text(fw['description'])}</span>")
            if fw.get("requires") and not is_command_installed(fw["requires"]):
                warn_label.set_markup(
                    f"<span color='orange'>⚠ {GLib.markup_escape_text(fw['requires'])} no está instalado</span>"
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
            conflict = _conflict_message(name)
            if conflict:
                error_label.set_markup(f"<span color='red'>{GLib.markup_escape_text(conflict)}</span>")
                return

            fw = FRAMEWORKS[fw_dropdown.get_selected()]
            create_btn.set_sensitive(False)
            create_btn.set_label("Creando…")
            error_label.set_markup("")

            def run():
                def on_progress(msg):
                    GLib.idle_add(progress_label.set_markup,
                                  f"<span color='gray' size='small'>{GLib.markup_escape_text(msg)}</span>")
                ok, err = scaffold_project(fw, name, projects_dir, on_progress)
                if not ok:
                    GLib.idle_add(error_label.set_markup,
                                  f"<span color='red'>Error: {GLib.markup_escape_text(err or '')}</span>")
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
