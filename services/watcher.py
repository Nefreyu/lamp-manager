import logging
import threading
from pathlib import Path

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from config import settings

log = logging.getLogger(__name__)

SERVICE_CHECK_SECONDS = 30


class ProjectWatcher:
    """Regenera el dashboard al detectar cambios de rama en los .git/HEAD de los proyectos
    o cambios de estado en los servicios."""

    def __init__(self):
        self._monitors: dict[str, Gio.FileMonitor] = {}
        self._dir_monitor: Gio.FileMonitor | None = None
        self._pending_regen = False
        self._service_statuses: dict[str, bool] = {}
        self._service_timer_id: int | None = None

    def start(self):
        self._refresh_watches()
        self._service_statuses = _read_service_statuses()
        self._service_timer_id = GLib.timeout_add_seconds(SERVICE_CHECK_SECONDS, self._on_service_timer)
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
        if self._service_timer_id is not None:
            GLib.source_remove(self._service_timer_id)
            self._service_timer_id = None

    def check_services(self) -> None:
        """Regenera el dashboard si algún servicio ha cambiado de estado desde la última comprobación."""
        statuses = _read_service_statuses()
        if statuses == self._service_statuses:
            return
        log.debug("Cambio de estado en los servicios: %s", statuses)
        self._service_statuses = statuses
        self._schedule_regen()

    def _on_service_timer(self):
        try:
            self.check_services()
        except Exception as e:
            log.warning("Error al comprobar el estado de los servicios: %s", e)
        return True

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
            log.debug("Dashboard regenerado")
        except Exception as e:
            log.warning("Error al regenerar dashboard: %s", e)


def _read_service_statuses() -> dict[str, bool]:
    from services.systemd import SERVICES, get_status, is_installed
    return {s["id"]: get_status(s["id"]) for s in SERVICES if not s.get("web_only") and is_installed(s)}
