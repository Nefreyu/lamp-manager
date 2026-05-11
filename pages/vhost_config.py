import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from services.vhosts import get_docroot, update_docroot, vhost_config_path
from services.systemd import _run_sudo_output, _sudo_write_file


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
        self.append(entry_box)

        save_docroot_btn = Gtk.Button(label="Guardar")
        save_docroot_btn.add_css_class("suggested-action")
        save_docroot_btn.set_halign(Gtk.Align.START)
        save_docroot_btn.connect("clicked", self.on_save_docroot)
        self.append(save_docroot_btn)

        self.append(Gtk.Separator())

        raw_label = Gtk.Label(label="Configuración completa")
        raw_label.set_xalign(0)
        self.append(raw_label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        self.raw_view = Gtk.TextView()
        self.raw_view.set_monospace(True)
        self.raw_view.set_top_margin(8)
        self.raw_view.set_bottom_margin(8)
        self.raw_view.set_left_margin(8)
        self.raw_view.set_right_margin(8)
        scrolled.set_child(self.raw_view)
        self.append(scrolled)

        save_raw_btn = Gtk.Button(label="Guardar configuración completa")
        save_raw_btn.set_halign(Gtk.Align.START)
        save_raw_btn.connect("clicked", self.on_save_raw)
        self.append(save_raw_btn)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.append(self.status_label)

    def load(self, name: str):
        self._name = name
        self.title.set_markup(f"<span size='x-large' weight='bold'>{name}.test</span>")
        self.docroot_entry.set_text(get_docroot(name))
        content = _run_sudo_output(["cat", str(vhost_config_path(name))]) or ""
        self.raw_view.get_buffer().set_text(content)
        self.status_label.set_markup("")

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
        ok = update_docroot(self._name, new_docroot)
        if ok:
            self.load(self._name)
            self._show_status(True, "DocumentRoot actualizado correctamente")
        else:
            self._show_status(False, "Error al actualizar el DocumentRoot")

    def on_save_raw(self, button):
        buf = self.raw_view.get_buffer()
        content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        ok = _sudo_write_file(str(vhost_config_path(self._name)), content)
        if ok:
            self.load(self._name)
            self._show_status(True, "Configuración guardada correctamente")
        else:
            self._show_status(False, "Error al guardar la configuración")

    def _show_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{message}</span>")
        GLib.timeout_add_seconds(3, lambda: self.status_label.set_markup("") or False)
