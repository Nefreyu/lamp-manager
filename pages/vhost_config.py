import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from pathlib import Path

from config import settings
from services.vhosts import (
    get_docroot, update_docroot, vhost_config_path, get_vhost_log_paths, ensure_vhost_logs,
    plan_project_rename, rename_project, save_vhost_config, docroot_location_error,
)
from services.systemd import _run_sudo_output
from pages.log_viewer import LogViewer


class VHostConfigPage(Gtk.Box):
    def __init__(self, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self._name = None

        back_btn = Gtk.Button(label="Virtual Hosts")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.set_halign(Gtk.Align.START)
        back_btn.connect("clicked", lambda _: navigate_to("vhosts"))
        self.append(back_btn)

        self.title = Gtk.Label()
        self.title.set_xalign(0)
        self.append(self.title)
        self.append(Gtk.Separator())

        # DocumentRoot — siempre visible, fuera del notebook
        docroot_label = Gtk.Label(label="DocumentRoot")
        docroot_label.set_xalign(0)
        self.append(docroot_label)

        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.docroot_entry = Gtk.Entry()
        self.docroot_entry.set_hexpand(True)
        self.docroot_entry.connect("activate", lambda _: self.on_save_docroot(None))
        entry_box.append(self.docroot_entry)

        folder_btn = Gtk.Button()
        folder_btn.set_icon_name("folder-open-symbolic")
        folder_btn.set_tooltip_text("Seleccionar directorio")
        folder_btn.connect("clicked", self.on_choose_folder)
        entry_box.append(folder_btn)

        save_docroot_btn = Gtk.Button(label="Guardar")
        save_docroot_btn.add_css_class("suggested-action")
        save_docroot_btn.set_valign(Gtk.Align.CENTER)
        save_docroot_btn.connect("clicked", self.on_save_docroot)
        entry_box.append(save_docroot_btn)
        self.append(entry_box)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.status_label.set_wrap(True)
        self.status_label.set_selectable(True)
        self.append(self.status_label)
        self._status_timeout_id: int | None = None

        self.append(Gtk.Separator())

        # Notebook: config raw + logs
        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        # ── Pestaña Configuración ──
        config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        config_box.set_margin_top(12)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.raw_view = Gtk.TextView()
        self.raw_view.set_monospace(True)
        self.raw_view.set_top_margin(8)
        self.raw_view.set_bottom_margin(8)
        self.raw_view.set_left_margin(8)
        self.raw_view.set_right_margin(8)
        scrolled.set_child(self.raw_view)
        config_box.append(scrolled)

        notebook.append_page(config_box, Gtk.Label(label="Configuración"))

        save_raw_btn = Gtk.Button(label="Guardar configuración")
        save_raw_btn.add_css_class("suggested-action")
        save_raw_btn.set_halign(Gtk.Align.START)
        save_raw_btn.connect("clicked", self.on_save_raw)
        self.append(save_raw_btn)

        # ── Pestaña Log de errores ──
        self._error_log_viewer = LogViewer("/dev/null")
        self._error_log_viewer.set_margin_top(12)
        notebook.append_page(self._error_log_viewer, Gtk.Label(label="Log de errores"))

        # ── Pestaña Log de accesos ──
        self._access_log_viewer = LogViewer("/dev/null")
        self._access_log_viewer.set_margin_top(12)
        notebook.append_page(self._access_log_viewer, Gtk.Label(label="Log de accesos"))

    def load(self, name: str):
        self._name = name
        self.title.set_markup(f"<span size='x-large' weight='bold'>{GLib.markup_escape_text(name)}.test</span>")
        ensure_vhost_logs(name)
        self.docroot_entry.set_text(get_docroot(name))
        content = _run_sudo_output(["cat", str(vhost_config_path(name))]) or ""
        self.raw_view.get_buffer().set_text(content)
        self.status_label.set_markup("")
        error_log, access_log = get_vhost_log_paths(name)
        self._error_log_viewer.set_path(error_log)
        self._access_log_viewer.set_path(access_log)

    def on_choose_folder(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Seleccionar DocumentRoot")
        dialog.select_folder(self.get_root(), None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.docroot_entry.set_text(folder.get_path())
        except Exception:
            pass

    def on_save_docroot(self, button):
        new_docroot = self.docroot_entry.get_text().strip()
        if not new_docroot:
            self._show_status(False, "El DocumentRoot no puede estar vacío")
            return
        projects_dir = settings.get("general", "projects_dir")
        location_error = docroot_location_error(new_docroot, projects_dir)
        if location_error:
            self._show_status(False, location_error)
            return
        if Path(new_docroot).is_dir():
            ok, error = update_docroot(self._name, new_docroot, projects_dir)
            if ok:
                self.load(self._name)
                self._show_status(True, "DocumentRoot actualizado correctamente")
            else:
                self._show_status(False, f"Error al actualizar el DocumentRoot:\n{error}")
            return

        rename = plan_project_rename(self._name, new_docroot, projects_dir)
        if rename is None:
            self._show_status(False, f"El directorio {new_docroot} no existe")
            return
        src, dst = rename
        dialog = Gtk.AlertDialog()
        dialog.set_message("¿Renombrar la carpeta del proyecto?")
        dialog.set_detail(
            f"La carpeta {dst.name} no existe.\n\n"
            f"Se renombrará {src} a {dst} y se actualizarán Apache y Nginx. "
            f"El dominio {self._name}.test no cambia."
        )
        dialog.set_buttons(["Cancelar", "Renombrar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(
            self.get_root(), None,
            lambda d, r: self._on_rename_confirmed(d, r, new_docroot, src, dst),
        )

    def _on_rename_confirmed(self, dialog, result, new_docroot: str, src: Path, dst: Path):
        try:
            if dialog.choose_finish(result) != 1:
                return
        except GLib.Error:
            return
        ok, error = rename_project(self._name, new_docroot, src, dst, settings.get("general", "projects_dir"))
        self.load(self._name)
        if ok:
            self._show_status(True, f"Carpeta renombrada a {dst.name} y DocumentRoot actualizado")
        else:
            self._show_status(False, f"Error al renombrar la carpeta; se ha dejado como estaba:\n{error}")

    def on_save_raw(self, button):
        buf = self.raw_view.get_buffer()
        content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        ok, error = save_vhost_config(self._name, content, settings.get("general", "projects_dir"))
        if ok:
            self.load(self._name)
            self._show_status(True, "Configuración guardada y Apache recargado")
        else:
            # No se recarga el editor: así el usuario conserva su texto para corregirlo
            self._show_status(False, f"No se ha guardado.\n{error}")

    def _show_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{GLib.markup_escape_text(message)}</span>")
        if self._status_timeout_id is not None:
            GLib.source_remove(self._status_timeout_id)
            self._status_timeout_id = None
        # Los errores se quedan visibles hasta la siguiente acción
        if success:
            self._status_timeout_id = GLib.timeout_add_seconds(5, self._clear_status)

    def _clear_status(self) -> bool:
        self.status_label.set_markup("")
        self._status_timeout_id = None
        return False
