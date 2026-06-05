import gi
import logging
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

import threading
from datetime import datetime
from services.vhosts import list_trash, restore_vhost, purge_trash_item, purge_all_trash

log = logging.getLogger(__name__)


class VHostTrashPage(Gtk.Box):
    def __init__(self, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._navigate_to = navigate_to
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        back_btn = Gtk.Button(label="Virtual Hosts")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.set_halign(Gtk.Align.START)
        back_btn.connect("clicked", lambda _: navigate_to("vhosts"))
        self.append(back_btn)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Papelera</span>")
        title.set_hexpand(True)
        title.set_xalign(0)
        header_box.append(title)

        self.empty_btn = Gtk.Button()
        self.empty_btn.add_css_class("destructive-action")
        self.empty_btn.connect("clicked", self._on_empty_trash)
        empty_btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        empty_btn_content.append(Gtk.Image.new_from_icon_name("edit-clear-all-symbolic"))
        empty_btn_content.append(Gtk.Label(label="Vaciar papelera"))
        self.empty_btn.set_child(empty_btn_content)
        header_box.append(self.empty_btn)

        self.append(header_box)
        self.append(Gtk.Separator())

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.append(self.status_label)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.list_box)

    def refresh(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        items = list_trash()
        self.empty_btn.set_visible(bool(items))

        if not items:
            empty = Gtk.Label(label="La papelera está vacía.")
            empty.set_xalign(0)
            self.list_box.append(empty)
            return

        for meta in items:
            self.list_box.append(self._make_row(meta))

    def _on_empty_trash(self, button):
        dialog = Gtk.AlertDialog()
        dialog.set_message("¿Vaciar la papelera?")
        dialog.set_detail(
            "Todos los proyectos, archivos y bases de datos de la papelera "
            "se borrarán para siempre. Esta acción no se puede deshacer."
        )
        dialog.set_buttons(["Cancelar", "Vaciar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, self._on_empty_confirmed)

    def _on_empty_confirmed(self, dialog, result):
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            self.empty_btn.set_sensitive(False)
            threading.Thread(target=self._run_empty_trash, daemon=True).start()

    def _run_empty_trash(self):
        ok = purge_all_trash()
        GLib.idle_add(self._after_empty_trash, ok)

    def _after_empty_trash(self, ok: bool):
        self.empty_btn.set_sensitive(True)
        if not ok:
            self._set_status(False, "Error al vaciar la papelera.")
        self.refresh()

    def _make_row(self, meta: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)

        name_label = Gtk.Label(label=f"{meta['name']}.test")
        name_label.set_xalign(0)
        info.append(name_label)

        try:
            dt = datetime.fromisoformat(meta["deleted_at"])
            date_str = dt.strftime("%d/%m/%Y %H:%M")
        except Exception as e:
            log.warning("Fecha inválida en metadatos de papelera '%s': %s", meta.get("name"), e)
            date_str = "—"

        badges = []
        if meta.get("has_db"):
            badges.append("BD")
        badge_str = f"  ·  {' · '.join(badges)}" if badges else ""
        date_label = Gtk.Label()
        date_label.set_markup(f"<span color='gray' size='small'>{date_str}{badge_str}</span>")
        date_label.set_xalign(0)
        info.append(date_label)

        row.append(info)

        restore_btn = Gtk.Button(label="Restaurar")
        restore_btn.set_icon_name("edit-undo-symbolic")
        restore_btn.set_valign(Gtk.Align.CENTER)
        restore_btn.connect("clicked", self._on_restore, meta, restore_btn)
        row.append(restore_btn)

        purge_btn = Gtk.Button()
        purge_btn.set_icon_name("edit-delete-symbolic")
        purge_btn.set_tooltip_text("Eliminar definitivamente")
        purge_btn.set_valign(Gtk.Align.CENTER)
        purge_btn.add_css_class("destructive-action")
        purge_btn.connect("clicked", self._on_purge, meta)
        row.append(purge_btn)

        return row

    def _on_restore(self, button, meta, restore_btn):
        restore_btn.set_sensitive(False)
        restore_btn.set_label("Restaurando…")

        def run():
            ok = restore_vhost(meta["trash_id"])
            GLib.idle_add(self._after_restore, ok, meta["name"])

        threading.Thread(target=run, daemon=True).start()

    def _after_restore(self, ok: bool, name: str):
        if ok:
            self._navigate_to("vhosts")
        else:
            self._set_status(False, f"Error al restaurar {name}.test.")
            self.refresh()

    def _on_purge(self, button, meta):
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"¿Eliminar {meta['name']} definitivamente?")
        dialog.set_detail(
            "Los archivos y la base de datos se borrarán para siempre.\n"
            "Esta acción no se puede deshacer."
        )
        dialog.set_buttons(["Cancelar", "Eliminar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, lambda d, r: self._on_purge_confirmed(d, r, meta))

    def _on_purge_confirmed(self, dialog, result, meta):
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            purge_trash_item(meta["trash_id"])
            self.refresh()

    def _set_status(self, success: bool, message: str):
        color = "green" if success else "red"
        self.status_label.set_markup(f"<span color='{color}'>{message}</span>")
        GLib.timeout_add_seconds(5, lambda: self.status_label.set_markup("") or False)
