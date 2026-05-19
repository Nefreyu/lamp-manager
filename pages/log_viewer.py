import re
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from services.systemd import read_log_tail, clear_log

_TAG_COLORS = {
    "error":  "#e01b24",
    "crit":   "#e01b24",
    "alert":  "#e01b24",
    "emerg":  "#e01b24",
    "warn":   "#e66100",
    "warning":"#e66100",
    "notice": "#77767b",
    "info":   "#3584e4",
    "debug":  "#77767b",
}

# Apache:   [module:level]
_RE_APACHE  = re.compile(r'\[\w+:(error|warn|notice|info|debug|crit|alert|emerg)\]', re.IGNORECASE)
# PHP-FPM:  ] LEVEL:
_RE_PHP     = re.compile(r'\]\s+(WARNING|ERROR|NOTICE|INFO)\s*:', re.IGNORECASE)
# MySQL:    [Level]
_RE_MYSQL   = re.compile(r'\[(Warning|Error|Note|System)\]', re.IGNORECASE)


def _detect_level(line: str) -> str | None:
    m = _RE_APACHE.search(line) or _RE_PHP.search(line) or _RE_MYSQL.search(line)
    return m.group(1).lower() if m else None


class LogViewer(Gtk.Box):
    def __init__(self, path: str, lines: int = 200, refresh_secs: int = 3):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._path = path
        self._lines = lines
        self._refresh_secs = refresh_secs
        self._timeout_id = None

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self._path_label = Gtk.Label()
        self._path_label.set_markup(f"<span size='small' color='gray'>{path}</span>")
        self._path_label.set_xalign(0)
        self._path_label.set_hexpand(True)
        header.append(self._path_label)

        clear_btn = Gtk.Button()
        clear_btn.set_icon_name("edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Vaciar log")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._on_clear_clicked)
        header.append(clear_btn)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Actualizar ahora")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.connect("clicked", lambda _: self._load())
        header.append(refresh_btn)

        auto_label = Gtk.Label(label="Auto")
        header.append(auto_label)

        self._auto_switch = Gtk.Switch()
        self._auto_switch.set_valign(Gtk.Align.CENTER)
        self._auto_switch.set_active(True)
        self._auto_switch.connect("state-set", self._on_auto_toggled)
        header.append(self._auto_switch)

        self.append(header)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_vexpand(True)

        self._textview = Gtk.TextView()
        self._textview.set_editable(False)
        self._textview.set_monospace(True)
        self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._textview.set_left_margin(8)
        self._textview.set_right_margin(8)
        self._textview.set_top_margin(8)
        self._textview.set_bottom_margin(8)
        self._buffer = self._textview.get_buffer()
        self._last_content = None

        self._tags = {
            level: self._buffer.create_tag(level, foreground=color)
            for level, color in _TAG_COLORS.items()
        }

        self._scrolled.set_child(self._textview)
        self.append(self._scrolled)

        self._scrolled.connect("realize", lambda _: GLib.idle_add(self._scroll_to_bottom))
        self._load()
        self._start_auto_refresh()
        self.connect("destroy", lambda _: self._stop_auto_refresh())

    def set_path(self, path: str):
        self._path = path
        self._path_label.set_markup(f"<span size='small' color='gray'>{path}</span>")
        self._last_content = None
        self._load()

    def _insert_colored(self, text: str):
        for line in text.splitlines(keepends=True):
            level = _detect_level(line)
            tag = self._tags.get(level) if level else None
            end = self._buffer.get_end_iter()
            if tag:
                self._buffer.insert_with_tags(end, line, tag)
            else:
                self._buffer.insert(end, line)

    def _load(self):
        content = read_log_tail(self._path, self._lines)
        if content is None:
            text = f"Archivo no encontrado: {self._path}"
        elif content.strip() == "":
            text = "(El log está vacío)"
        else:
            text = content

        if text == self._last_content:
            return

        adj = self._scrolled.get_vadjustment()
        at_bottom = (
            self._last_content is None
            or adj.get_upper() - adj.get_page_size() - adj.get_value() < 20
        )

        if self._last_content is not None and text.startswith(self._last_content):
            self._insert_colored(text[len(self._last_content):])
        else:
            self._buffer.set_text("")
            self._insert_colored(text)

        self._last_content = text

        if at_bottom:
            GLib.idle_add(self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        adj = self._scrolled.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def _start_auto_refresh(self):
        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add_seconds(self._refresh_secs, self._on_tick)

    def _stop_auto_refresh(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def _on_tick(self):
        self._load()
        return True

    def _on_auto_toggled(self, switch, state):
        if state:
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()
        return False

    def _on_clear_clicked(self, button):
        dialog = Gtk.AlertDialog()
        dialog.set_message("¿Vaciar el log?")
        dialog.set_detail(
            "El archivo de log se truncará. Apache seguirá escribiendo "
            "en el mismo archivo sin necesidad de reiniciarlo."
        )
        dialog.set_buttons(["Cancelar", "Vaciar"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.get_root(), None, self._on_clear_confirmed)

    def _on_clear_confirmed(self, dialog, result):
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            clear_log(self._path)
            self._last_content = None
            self._load()
