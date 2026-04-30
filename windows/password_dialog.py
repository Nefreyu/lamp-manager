import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class PasswordDialog(Gtk.Window):
    def __init__(self, parent, on_success, on_cancel):
        super().__init__(title="Autenticación")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(300, -1)
        self.on_success = on_success
        self.on_cancel = on_cancel

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
        self.password_entry.connect("activate", self.on_accept)
        box.append(self.password_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_markup("<span color='red'> </span>")
        box.append(self.error_label)

        # Botones
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons_box.set_halign(Gtk.Align.END)
        box.append(buttons_box)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        buttons_box.append(cancel_btn)

        accept_btn = Gtk.Button(label="Aceptar")
        accept_btn.add_css_class("suggested-action")
        accept_btn.connect("clicked", self.on_accept)
        buttons_box.append(accept_btn)

    def on_accept(self, *args):
        self.on_success(self.password_entry.get_text())

    def on_cancel_clicked(self, *args):
        self.on_cancel()

    def show_error(self):
        self.error_label.set_markup("<span color='red'>Contraseña incorrecta, inténtalo de nuevo.</span>")
        self.password_entry.set_text("")
        self.password_entry.grab_focus()