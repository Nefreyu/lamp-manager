import gi
import logging
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from pathlib import Path

log = logging.getLogger(__name__)

from services.mysql import (
    get_conf_path, MYSQL_ERROR_LOG, MYSQL_SLOW_LOG,
    list_databases, create_database, drop_database,
    list_users, create_user, drop_user, grant_all,
    get_last_error,
)
from pages.log_viewer import LogViewer


class CreateUserDialog(Gtk.Dialog):
    def __init__(self, parent, databases: list[str], on_created):
        super().__init__(title="Crear usuario", transient_for=parent, modal=True)
        self.set_default_size(360, -1)
        self._on_created = on_created

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        grid = Gtk.Grid()
        grid.set_row_spacing(8)
        grid.set_column_spacing(12)

        grid.attach(Gtk.Label(label="Usuario", xalign=0), 0, 0, 1, 1)
        self._user_entry = Gtk.Entry()
        self._user_entry.set_hexpand(True)
        grid.attach(self._user_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Host", xalign=0), 0, 1, 1, 1)
        self._host_entry = Gtk.Entry()
        self._host_entry.set_text("localhost")
        grid.attach(self._host_entry, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Contraseña", xalign=0), 0, 2, 1, 1)
        self._pass_entry = Gtk.PasswordEntry()
        self._pass_entry.set_show_peek_icon(True)
        self._pass_entry.set_hexpand(True)
        grid.attach(self._pass_entry, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Acceso a", xalign=0), 0, 3, 1, 1)
        self._db_combo = Gtk.ComboBoxText()
        self._db_combo.append("", "Sin asignar")
        for db in databases:
            self._db_combo.append(db, db)
        self._db_combo.set_active(0)
        grid.attach(self._db_combo, 1, 3, 1, 1)

        content.append(grid)

        self._status = Gtk.Label(label="")
        self._status.set_xalign(0)
        content.append(self._status)

        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        ok_btn = self.add_button("Crear", Gtk.ResponseType.OK)
        ok_btn.add_css_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self.connect("response", self._on_response)

    def _on_response(self, dialog, response):
        if response != Gtk.ResponseType.OK:
            self.close()
            return

        username = self._user_entry.get_text().strip()
        host = self._host_entry.get_text().strip() or "localhost"
        password = self._pass_entry.get_text()
        database = self._db_combo.get_active_id()

        if not username:
            self._status.set_markup("<span color='red'>El nombre de usuario es obligatorio</span>")
            return
        if not password:
            self._status.set_markup("<span color='red'>La contraseña es obligatoria</span>")
            return

        ok = create_user(username, host, password)
        if ok and database:
            grant_all(username, host, database)

        if ok:
            self._on_created()
            self.close()
        else:
            self._status.set_markup("<span color='red'>Error al crear el usuario (¿ya existe?)</span>")


class DatabaseRow(Gtk.ListBoxRow):
    def __init__(self, name: str, on_delete):
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(8)

        label = Gtk.Label(label=name)
        label.set_hexpand(True)
        label.set_xalign(0)
        box.append(label)

        del_btn = Gtk.Button()
        del_btn.set_icon_name("edit-delete-symbolic")
        del_btn.set_tooltip_text("Eliminar base de datos")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.add_css_class("destructive-action")
        del_btn.add_css_class("flat")
        del_btn.connect("clicked", lambda _: on_delete(name))
        box.append(del_btn)

        self.set_child(box)


class UserRow(Gtk.ListBoxRow):
    def __init__(self, username: str, host: str, databases: list[str], on_delete):
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(8)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        label = Gtk.Label(label=f"{username}@{host}")
        label.set_xalign(0)
        text_box.append(label)

        db_text = ", ".join(databases) if databases else "Sin acceso a bases de datos"
        db_label = Gtk.Label()
        db_label.set_markup(f"<span size='small' color='gray'>{GLib.markup_escape_text(db_text)}</span>")
        db_label.set_xalign(0)
        text_box.append(db_label)

        box.append(text_box)

        del_btn = Gtk.Button()
        del_btn.set_icon_name("edit-delete-symbolic")
        del_btn.set_tooltip_text("Eliminar usuario")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.add_css_class("destructive-action")
        del_btn.add_css_class("flat")
        del_btn.connect("clicked", lambda _: on_delete(username, host))
        box.append(del_btn)

        self.set_child(box)


class MysqlConfigPage(Gtk.Box):
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

        self.append(self._file_row("Configuración principal", get_conf_path(), "document-edit-symbolic"))
        self.append(Gtk.Separator())

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        notebook.append_page(self._build_databases_tab(), Gtk.Label(label="Bases de datos"))
        notebook.append_page(self._build_users_tab(), Gtk.Label(label="Usuarios"))

        self.connect("map", self._on_map)

        error_log = LogViewer(MYSQL_ERROR_LOG)
        error_log.set_margin_top(12)
        notebook.append_page(error_log, Gtk.Label(label="Log de errores"))

        slow_log = LogViewer(MYSQL_SLOW_LOG)
        slow_log.set_margin_top(12)
        notebook.append_page(slow_log, Gtk.Label(label="Log de consultas lentas"))

    def _build_databases_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(12)

        create_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._db_entry = Gtk.Entry()
        self._db_entry.set_placeholder_text("Nombre de la base de datos")
        self._db_entry.set_hexpand(True)
        self._db_entry.connect("activate", lambda _: self._on_create_db())
        create_row.append(self._db_entry)

        create_btn = Gtk.Button(label="Crear")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", lambda _: self._on_create_db())
        create_row.append(create_btn)
        box.append(create_row)

        self._db_status = Gtk.Label(label="")
        self._db_status.set_xalign(0)
        box.append(self._db_status)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self._db_listbox = Gtk.ListBox()
        self._db_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._db_listbox.add_css_class("boxed-list")
        scrolled.set_child(self._db_listbox)
        box.append(scrolled)

        return box

    def _build_users_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(12)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._user_status = Gtk.Label(label="")
        self._user_status.set_hexpand(True)
        self._user_status.set_xalign(0)
        header.append(self._user_status)

        create_btn = Gtk.Button(label="Crear usuario")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", self._on_create_user_clicked)
        header.append(create_btn)
        box.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self._user_listbox = Gtk.ListBox()
        self._user_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._user_listbox.add_css_class("boxed-list")
        scrolled.set_child(self._user_listbox)
        box.append(scrolled)

        return box

    def _on_map(self, _):
        self._load_databases()
        self._load_users()

    def _load_databases(self):
        while child := self._db_listbox.get_first_child():
            self._db_listbox.remove(child)
        dbs = list_databases()
        if dbs is None:
            err = get_last_error()
            msg = f"No se pudo conectar con MySQL: {err}" if err else "No se pudo conectar con MySQL"
            self._show_db_status(False, msg)
            return
        for name in dbs:
            self._db_listbox.append(DatabaseRow(name, self._on_delete_db))

    def _load_users(self):
        while child := self._user_listbox.get_first_child():
            self._user_listbox.remove(child)
        for username, host, databases in list_users():
            self._user_listbox.append(UserRow(username, host, databases, self._on_delete_user))

    def _on_create_db(self):
        name = self._db_entry.get_text().strip()
        if not name:
            return
        ok = create_database(name)
        if ok:
            self._db_entry.set_text("")
            self._load_databases()
            self._show_db_status(True, f"Base de datos '{name}' creada")
        else:
            self._show_db_status(False, "Error al crear la base de datos (¿ya existe?)")

    def _on_delete_db(self, name: str):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Eliminar '{name}'?")
        dialog.set_detail("Se eliminarán todos los datos. Esta acción no se puede deshacer.")
        dialog.set_buttons(["Cancelar", "Eliminar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, lambda d, r: self._confirm_delete_db(d, r, name))

    def _confirm_delete_db(self, dialog, result, name: str):
        try:
            if dialog.choose_finish(result) != 1:
                return
        except Exception:
            return
        ok = drop_database(name)
        if ok:
            self._load_databases()
            self._show_db_status(True, f"Base de datos '{name}' eliminada")
        else:
            self._show_db_status(False, "Error al eliminar la base de datos")

    def _on_create_user_clicked(self, button):
        dbs = list_databases() or []
        dialog = CreateUserDialog(self.get_root(), dbs, self._load_users)
        dialog.present()

    def _on_delete_user(self, username: str, host: str):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Eliminar '{username}@{host}'?")
        dialog.set_detail("Se eliminará el usuario y todos sus privilegios.")
        dialog.set_buttons(["Cancelar", "Eliminar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, lambda d, r: self._confirm_delete_user(d, r, username, host))

    def _confirm_delete_user(self, dialog, result, username: str, host: str):
        try:
            if dialog.choose_finish(result) != 1:
                return
        except Exception:
            return
        ok = drop_user(username, host)
        if ok:
            self._load_users()
            self._show_user_status(True, f"Usuario '{username}@{host}' eliminado")
        else:
            self._show_user_status(False, "Error al eliminar el usuario")

    def _show_db_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self._db_status.set_markup(f"<span color='{color}'>{GLib.markup_escape_text(message)}</span>")
        if success:
            GLib.timeout_add_seconds(4, lambda: self._db_status.set_markup("") or False)

    def _show_user_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self._user_status.set_markup(f"<span color='{color}'>{GLib.markup_escape_text(message)}</span>")
        if success:
            GLib.timeout_add_seconds(4, lambda: self._user_status.set_markup("") or False)

    def _file_row(self, label: str, path: str, icon: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        name_label = Gtk.Label(label=label)
        name_label.set_xalign(0)
        name_label.set_hexpand(True)
        row.append(name_label)

        path_label = Gtk.Label()
        path_label.set_markup(f"<span color='gray' size='small'>{GLib.markup_escape_text(path)}</span>")
        row.append(path_label)

        btn = Gtk.Button()
        btn.set_icon_name(icon)
        btn.set_tooltip_text(path)
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_sensitive(Path(path).exists())
        btn.connect("clicked", lambda _, p=path: self._open_file(p))
        row.append(btn)

        return row

    def _open_file(self, path: str):
        try:
            Gio.AppInfo.launch_default_for_uri(f"admin://{path}", None)
        except Exception:
            try:
                Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
            except Exception as e:
                log.warning("No se pudo abrir el archivo %s: %s", path, e)
