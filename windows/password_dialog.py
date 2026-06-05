import logging
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from services.systemd import validate_password

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class PasswordDialog(Gtk.Window):
    def __init__(self, parent, on_success, on_cancel):
        super().__init__(title="Autenticación")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(300, -1)
        self._on_success = on_success
        self._on_cancel = on_cancel
        self._attempts = 0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        self.set_child(box)

        label = Gtk.Label(label="Introduce tu contraseña de administrador:")
        label.set_xalign(0)
        box.append(label)

        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.connect("activate", self._on_accept)
        box.append(self.password_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_markup("<span> </span>")
        box.append(self.error_label)

        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons_box.set_halign(Gtk.Align.END)
        box.append(buttons_box)

        self.cancel_btn = Gtk.Button(label="Cancelar")
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        buttons_box.append(self.cancel_btn)

        self.accept_btn = Gtk.Button(label="Aceptar")
        self.accept_btn.add_css_class("suggested-action")
        self.accept_btn.connect("clicked", self._on_accept)
        buttons_box.append(self.accept_btn)

    def _on_accept(self, *args):
        password = self.password_entry.get_text()
        self._set_loading(True)
        threading.Thread(target=self._validate, args=(password,), daemon=True).start()

    def _validate(self, password):
        ok = validate_password(password)
        GLib.idle_add(self._on_validate_result, password, ok)

    def _on_validate_result(self, password, ok):
        if ok:
            self._on_success(password)
        else:
            self._attempts += 1
            log.warning("Intento de contraseña fallido (%d/%d)", self._attempts, MAX_ATTEMPTS)
            remaining = MAX_ATTEMPTS - self._attempts
            if remaining <= 0:
                self._on_cancel()
            else:
                self._set_loading(False)
                msg = "Último intento." if remaining == 1 else f"Quedan {remaining} intentos."
                self.error_label.set_markup(
                    f"<span color='red'>Contraseña incorrecta. {msg}</span>"
                )
                self.password_entry.set_text("")
                self.password_entry.grab_focus()

    def _set_loading(self, loading):
        self.accept_btn.set_sensitive(not loading)
        self.cancel_btn.set_sensitive(not loading)
        self.password_entry.set_sensitive(not loading)
        if loading:
            self.error_label.set_markup("<span color='gray'>Verificando…</span>")

    def _on_cancel_clicked(self, *args):
        self._on_cancel()
