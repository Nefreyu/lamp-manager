import logging
import threading
from pathlib import Path

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from config import settings

log = logging.getLogger(__name__)


class ProjectWatcher:
    """Vigila los archivos .git/HEAD de los proyectos y regenera el dashboard al detectar cambios de rama."""

    def __init__(self):
        self._monitors: dict[str, Gio.FileMonitor] = {}
        self._dir_monitor: Gio.FileMonitor | None = None
        self._pending_regen = False

    def start(self):
        self._refresh_watches()
        projects_dir = settings.get("general", "projects_dir")
        d = Gio.File.new_for_path(projects_dir)
        try:
            self._dir_monitor = d.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._dir_monitor.connect("changed", self._on_dir_changed)
        except Exception as e:
            log.warning("No se pudo vigilar el directorio de proyectos: %s", e)

    def stop(self):
        for m in self._monitors.values():
            m.cancel()
        self._monitors.clear()
        if self._dir_monitor:
            self._dir_monitor.cancel()
            self._dir_monitor = None

    def _refresh_watches(self):
        for m in self._monitors.values():
            m.cancel()
        self._monitors.clear()

        projects_dir = settings.get("general", "projects_dir")
        base = Path(projects_dir)
        if not base.exists():
            return

        for project_dir in base.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue
            head = project_dir / ".git" / "HEAD"
            if head.exists():
                self._watch_head(head)

        log.debug("Vigilando %d repos git", len(self._monitors))

    def _watch_head(self, path: Path):
        try:
            f = Gio.File.new_for_path(str(path))
            m = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
            m.connect("changed", self._on_head_changed)
            self._monitors[str(path)] = m
        except Exception as e:
            log.warning("No se pudo vigilar %s: %s", path, e)

    def _on_head_changed(self, monitor, file, other_file, event_type):
        if event_type in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED):
            log.debug("Cambio de rama detectado en %s", file.get_path())
            self._schedule_regen()

    def _on_dir_changed(self, monitor, file, other_file, event_type):
        if event_type in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED):
            GLib.timeout_add(1000, self._refresh_and_regen)

    def _refresh_and_regen(self):
        self._refresh_watches()
        self._schedule_regen()
        return False

    def _schedule_regen(self):
        if not self._pending_regen:
            self._pending_regen = True
            GLib.timeout_add(500, self._do_regen)

    def _do_regen(self):
        self._pending_regen = False
        threading.Thread(target=self._regen_safe, daemon=True).start()
        return False

    def _regen_safe(self):
        try:
            from services.vhosts import generate_index_page
            generate_index_page()
            log.debug("Dashboard regenerado por cambio de rama")
        except Exception as e:
            log.warning("Error al regenerar dashboard: %s", e)
