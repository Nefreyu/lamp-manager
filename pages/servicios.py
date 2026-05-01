import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from services.systemd import (
    SERVICES, get_status, is_installed,
    start_service, stop_service,
    install_mailpit_service, uninstall_mailpit_service
)
from config import settings


class ServiceRow(Gtk.Box):
    def __init__(self, service: dict, navigate_to, on_changed=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.service = service
        self.service_id = service["id"]
        self.optional = service.get("optional", False)
        self.web_only = service.get("web_only", False)
        self.on_changed = on_changed
        self._updating = False

        # Nombre como botón de navegación
        name_btn = Gtk.Button(label=service["label"])
        name_btn.add_css_class("flat")
        name_btn.set_hexpand(True)
        name_btn.get_child().set_xalign(0)
        name_btn.connect("clicked", lambda _: navigate_to(f"service-{self.service_id}"))
        self.append(name_btn)

        # Indicador de estado
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        # Botón instalar/desinstalar (solo servicios opcionales)
        if self.optional:
            self.install_button = Gtk.Button()
            self.install_button.connect("clicked", self.on_install_clicked)
            self.append(self.install_button)

        # Botón abrir en navegador
        self.url = service.get("url")
        if self.url:
            self.link_button = Gtk.Button()
            self.link_button.set_icon_name("web-browser-symbolic")
            self.link_button.set_tooltip_text(self.url)
            self.link_button.set_valign(Gtk.Align.CENTER)
            self.link_button.connect("clicked", self.on_open_url)
            self.append(self.link_button)

        # Switch arrancar/parar (no aplica a servicios web_only)
        if not self.web_only:
            self.switch = Gtk.Switch()
            self.switch.set_valign(Gtk.Align.CENTER)
            self.switch.connect("state-set", self.on_switch_toggled)
            self.append(self.switch)

        self.refresh()

    def on_open_url(self, button):
        Gio.AppInfo.launch_default_for_uri(self.url, None)

    def refresh(self):
        self._updating = True

        if not is_installed(self.service):
            self.status_label.set_markup("<span color='orange'>⚠ no instalado</span>")
            if not self.web_only:
                self.switch.set_active(False)
                self.switch.set_sensitive(False)
            if self.url:
                self.link_button.set_sensitive(False)
            if self.optional:
                self.install_button.set_label("Instalar servicio")
        else:
            self.status_label.set_markup("")
            if self.web_only:
                if self.url:
                    self.link_button.set_sensitive(True)
            else:
                active = get_status(self.service_id)
                self.switch.set_active(active)
                self.switch.set_sensitive(True)
                if self.url:
                    self.link_button.set_sensitive(active)
            if self.optional:
                self.install_button.set_label("Desinstalar servicio")

        self._updating = False

    def on_switch_toggled(self, switch, state):
        if self._updating:
            return False
        if state:
            result = start_service(self.service_id)
        else:
            result = stop_service(self.service_id)
        print(f"Operación en {self.service_id}: {result}")
        def after_toggle():
            self.refresh()
            if self.on_changed:
                self.on_changed()
        GLib.timeout_add(500, after_toggle)
        return False

    def on_install_clicked(self, button):
        if is_installed(self.service):
            uninstall_mailpit_service()
        else:
            storage_enabled = settings.get("mailpit", "storage_enabled") == "true"
            storage_path = settings.get("mailpit", "storage_path")
            install_mailpit_service(storage_enabled, storage_path)
        GLib.timeout_add(500, self.refresh)


class ServiciosPage(Gtk.Box):
    def __init__(self, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Servicios</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        # Banner de aviso Apache+PHP-FPM
        self.fpm_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.fpm_banner.set_margin_bottom(4)

        banner_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        self.fpm_banner.append(banner_icon)

        banner_label = Gtk.Label(label="Apache está activo pero PHP-FPM no. Los proyectos PHP no funcionarán.")
        banner_label.set_hexpand(True)
        banner_label.set_xalign(0)
        self.fpm_banner.append(banner_label)

        fix_btn = Gtk.Button(label="Arrancar PHP-FPM")
        fix_btn.add_css_class("suggested-action")
        fix_btn.connect("clicked", self.on_start_fpm)
        self.fpm_banner.append(fix_btn)

        self.fpm_banner.set_visible(False)
        self.append(self.fpm_banner)

        self.rows = []
        for service in SERVICES:
            if service.get("hide_if_absent") and not is_installed(service):
                continue
            row = ServiceRow(service, navigate_to, on_changed=self._check_fpm_warning)
            self.append(row)
            self.rows.append(row)

        refresh_btn = Gtk.Button(label="Refrescar")
        refresh_btn.connect("clicked", self.on_refresh)
        refresh_btn.set_halign(Gtk.Align.START)
        self.append(refresh_btn)

        self._check_fpm_warning()

    def _check_fpm_warning(self):
        apache = next((s for s in SERVICES if s["id"] == "apache2"), None)
        fpm = next((s for s in SERVICES if s["id"] == "php8.5-fpm"), None)
        if apache and fpm and is_installed(apache) and is_installed(fpm):
            show = get_status("apache2") and not get_status("php8.5-fpm")
            self.fpm_banner.set_visible(show)

    def on_start_fpm(self, button):
        start_service("php8.5-fpm")
        GLib.timeout_add(500, self._after_start_fpm)

    def _after_start_fpm(self):
        self._check_fpm_warning()
        for row in self.rows:
            row.refresh()

    def on_refresh(self, button):
        for row in self.rows:
            row.refresh()
        self._check_fpm_warning()


class ServiceConfigPage(Gtk.Box):
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

        placeholder = Gtk.Label(
            label=f"Sección para la configuración del servicio de {service['label']}"
        )
        placeholder.set_xalign(0)
        self.append(placeholder)
