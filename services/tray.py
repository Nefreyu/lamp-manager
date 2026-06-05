import os
import gi
import logging
from pathlib import Path
from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

gi.require_version('Dbusmenu', '0.4')
from gi.repository import Dbusmenu

_SNI_XML = """\
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Id"            type="s"  access="read"/>
    <property name="Category"      type="s"  access="read"/>
    <property name="Status"        type="s"  access="read"/>
    <property name="IconName"      type="s"  access="read"/>
    <property name="IconThemePath" type="s"  access="read"/>
    <property name="Title"         type="s"  access="read"/>
    <property name="Menu"          type="o"  access="read"/>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>"""


class SystemTray:
    def __init__(self, on_toggle: callable, on_quit: callable):
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._sni_props = {
            "Id":            GLib.Variant("s", "lamp-manager"),
            "Category":      GLib.Variant("s", "ApplicationStatus"),
            "Status":        GLib.Variant("s", "Active"),
            "IconName":      GLib.Variant("s", "io.github.nefreyu.LampManager"),
            "IconThemePath": GLib.Variant("s", str(Path.home() / ".local/share/icons")),
            "Title":         GLib.Variant("s", "LAMP Manager"),
            "Menu":          GLib.Variant("o", "/MenuBar"),
        }

    def start(self) -> bool:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._svc = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

            self._setup_menu()

            sni_node = Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
            self._bus.register_object(
                "/StatusNotifierItem",
                sni_node.interfaces[0],
                self._sni_call,
                self._get_sni_property,
                None,
            )

            Gio.bus_own_name_on_connection(
                self._bus, self._svc, Gio.BusNameOwnerFlags.NONE,
                self._on_name_acquired,
                self._on_name_lost,
            )
            return True
        except Exception as e:
            log.error("Error al iniciar el tray: %s", e)
            return False

    def set_window_visible(self, visible: bool):
        label = "Ocultar LAMP Manager" if visible else "Mostrar LAMP Manager"
        self._show_item.property_set(Dbusmenu.MENUITEM_PROP_LABEL, label)

    def _setup_menu(self):
        root = Dbusmenu.Menuitem.new()

        self._show_item = Dbusmenu.Menuitem.new()
        self._show_item.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Ocultar LAMP Manager")
        self._show_item.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        self._show_item.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        self._show_item.connect("item-activated", lambda item, ts: GLib.idle_add(self._on_toggle))
        root.child_append(self._show_item)

        sep = Dbusmenu.Menuitem.new()
        sep.property_set(Dbusmenu.MENUITEM_PROP_TYPE, Dbusmenu.CLIENT_TYPES_SEPARATOR)
        root.child_append(sep)

        quit_item = Dbusmenu.Menuitem.new()
        quit_item.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Salir")
        quit_item.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        quit_item.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        quit_item.connect("item-activated", lambda item, ts: GLib.idle_add(self._on_quit))
        root.child_append(quit_item)

        self._menu_server = Dbusmenu.Server(dbus_object="/MenuBar")
        self._menu_server.set_root(root)

    def _on_name_acquired(self, conn, name):
        try:
            self._bus.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (name,)),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
            self._bus.emit_signal(
                None, "/StatusNotifierItem",
                "org.kde.StatusNotifierItem", "NewIcon", None,
            )
            self._bus.emit_signal(
                None, "/StatusNotifierItem",
                "org.kde.StatusNotifierItem", "NewStatus",
                GLib.Variant("(s)", ("Active",)),
            )
        except Exception as e:
            log.error("Error al registrar con StatusNotifierWatcher: %s", e)

    def _on_name_lost(self, conn, name):
        pass

    def _get_sni_property(self, conn, sender, path, iface, prop):
        return self._sni_props.get(prop)

    def _sni_call(self, conn, sender, path, iface, method, params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self._on_toggle)
            invocation.return_value(None)
        else:
            invocation.return_value(None)
