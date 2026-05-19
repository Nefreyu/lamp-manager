import gi
gi.require_version("Secret", "1")
from gi.repository import Secret

_SCHEMA = Secret.Schema.new(
    "io.github.nefreyu.LampManager",
    Secret.SchemaFlags.NONE,
    {"application": Secret.SchemaAttributeType.STRING},
)
_ATTRS = {"application": "lamp-manager"}


def get_sudo_password() -> str | None:
    try:
        return Secret.password_lookup_sync(_SCHEMA, _ATTRS, None)
    except Exception:
        return None


def save_sudo_password(password: str) -> bool:
    try:
        return Secret.password_store_sync(
            _SCHEMA, _ATTRS,
            Secret.COLLECTION_DEFAULT,
            "LAMP Manager - contraseña sudo",
            password, None,
        )
    except Exception:
        return False


def clear_sudo_password() -> bool:
    try:
        return Secret.password_clear_sync(_SCHEMA, _ATTRS, None)
    except Exception:
        return False
