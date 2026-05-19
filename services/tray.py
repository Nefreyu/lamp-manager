import os
from gi.repository import Gio, GLib

_SNI_XML = """\
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Id"       type="s" access="read"/>
    <property name="Category" type="s" access="read"/>
    <property name="Status"   type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="Title"    type="s" access="read"/>
    <property name="Menu"     type="o" access="read"/>
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

_MENU_XML = """\
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version"       type="u"  access="read"/>
    <property name="TextDirection" type="s"  access="read"/>
    <property name="Status"        type="s"  access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg name="parentId"      type="i"          direction="in"/>
      <arg name="recursionDepth" type="i"         direction="in"/>
      <arg name="propertyNames" type="as"         direction="in"/>
      <arg name="revision"      type="u"          direction="out"/>
      <arg name="layout"        type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg name="ids"           type="ai"        direction="in"/>
      <arg name="propertyNames" type="as"        direction="in"/>
      <arg name="properties"    type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg name="id"    type="i" direction="in"/>
      <arg name="name"  type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg name="id"        type="i"  direction="in"/>
      <arg name="eventId"   type="s"  direction="in"/>
      <arg name="data"      type="v"  direction="in"/>
      <arg name="timestamp" type="u"  direction="in"/>
    </method>
    <method name="EventGroup">
      <arg name="events"   type="a(isvu)" direction="in"/>
      <arg name="idErrors" type="ai"      direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg name="id"         type="i" direction="in"/>
      <arg name="needUpdate" type="b" direction="out"/>
    </method>
    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent"   type="i"/>
    </signal>
  </interface>
</node>"""


def _v(inner: GLib.Variant) -> GLib.Variant:
    return GLib.Variant("v", inner)


class SystemTray:
    _SNI_PROPS = {
        "Id":       GLib.Variant("s", "lamp-manager"),
        "Category": GLib.Variant("s", "ApplicationStatus"),
        "Status":   GLib.Variant("s", "Active"),
        "IconName": GLib.Variant("s", "io.github.nefreyu.LampManager"),
        "Title":    GLib.Variant("s", "LAMP Manager"),
        "Menu":     GLib.Variant("o", "/MenuBar"),
    }
    _MENU_PROPS = {
        "Version":       GLib.Variant("u", 3),
        "TextDirection": GLib.Variant("s", "ltr"),
        "Status":        GLib.Variant("s", "normal"),
        "IconThemePath": GLib.Variant("as", []),
    }

    def __init__(self, on_toggle: callable, on_quit: callable):
        self._on_toggle = on_toggle
        self._on_quit = on_quit

    def start(self) -> bool:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            svc = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

            Gio.bus_own_name_on_connection(
                bus, svc, Gio.BusNameOwnerFlags.NONE, None, None
            )

            sni_node = Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
            bus.register_object(
                "/StatusNotifierItem",
                sni_node.interfaces[0],
                self._sni_call,
                lambda c, s, p, i, prop: self._SNI_PROPS.get(prop),
                None,
            )

            menu_node = Gio.DBusNodeInfo.new_for_xml(_MENU_XML)
            bus.register_object(
                "/MenuBar",
                menu_node.interfaces[0],
                self._menu_call,
                lambda c, s, p, i, prop: self._MENU_PROPS.get(prop),
                None,
            )

            bus.call(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (svc,)),
                None, Gio.DBusCallFlags.NONE, -1, None, None, None,
            )
            return True
        except Exception:
            return False

    def _sni_call(self, conn, sender, path, iface, method, params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self._on_toggle)
        invocation.return_value(None)

    def _menu_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "GetLayout":
            children = [
                _v(GLib.Variant("(ia{sv}av)", (1, {"label":   GLib.Variant("s", "Mostrar LAMP Manager"),
                                                    "enabled": GLib.Variant("b", True)}, []))),
                _v(GLib.Variant("(ia{sv}av)", (2, {"type": GLib.Variant("s", "separator")}, []))),
                _v(GLib.Variant("(ia{sv}av)", (3, {"label":   GLib.Variant("s", "Salir"),
                                                    "enabled": GLib.Variant("b", True)}, []))),
            ]
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (1, (0, {}, children))))

        elif method == "Event":
            item_id, event_id, *_ = params.unpack()
            if event_id == "clicked":
                if item_id == 1:
                    GLib.idle_add(self._on_toggle)
                elif item_id == 3:
                    GLib.idle_add(self._on_quit)
            invocation.return_value(None)

        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "EventGroup":
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "GetGroupProperties":
            invocation.return_value(GLib.Variant("(a(ia{sv}))", ([],)))
        elif method == "GetProperty":
            invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", ""),)))
        else:
            invocation.return_value(None)
