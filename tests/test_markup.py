import gi
import pytest

gi.require_version("Pango", "1.0")
from gi.repository import GLib, Pango

from services.recommendations import RECOMMENDATIONS
from services.vhosts import _DEFAULT_FRAMEWORKS


def parses(markup: str) -> bool:
    try:
        Pango.parse_markup(markup, -1, "\0")
        return True
    except GLib.Error:
        return False


RECOMMENDATION_TEXTS = [
    text
    for rec in RECOMMENDATIONS
    for text in [rec["label"], rec["description"], *(c["cmd"] for c in rec["commands"])]
]
FRAMEWORK_TEXTS = [fw[key] for fw in _DEFAULT_FRAMEWORKS for key in ("label", "description") if key in fw]


@pytest.mark.parametrize("text", RECOMMENDATION_TEXTS + FRAMEWORK_TEXTS)
def test_static_texts_render_once_escaped(text):
    assert parses(f"<span color='gray'>{GLib.markup_escape_text(text)}</span>")


def test_mailpit_command_breaks_markup_without_escaping():
    mailpit = next(r for r in RECOMMENDATIONS if r["id"] == "mailpit")
    cmd = mailpit["commands"][0]["cmd"]
    assert not parses(f"<tt>{cmd}</tt>")
    assert parses(f"<tt>{GLib.markup_escape_text(cmd)}</tt>")


@pytest.mark.parametrize("text", [
    "Error: <stdin>:1 composer & co",
    "/home/juan/www/R&D",
    "Could not find package laravel/<laravel>",
])
def test_external_texts_render_once_escaped(text):
    assert not parses(f"<span>{text}</span>")
    assert parses(f"<span>{GLib.markup_escape_text(text)}</span>")
