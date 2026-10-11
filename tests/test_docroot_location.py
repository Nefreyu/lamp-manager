import pytest

import services.vhosts as vhosts
from services.vhosts import docroot_location_error, docroots_in_config, list_vhosts_outside

PROJECTS = "/home/juan/www"

CONFIG = """<VirtualHost *:80>
    ServerName demo.test
    Redirect permanent / https://demo.test:443/
</VirtualHost>

<VirtualHost *:443>
    ServerName demo.test
    DocumentRoot /home/juan/www/demo/public
    <Directory /home/juan/www/demo/public>
        Require all granted
    </Directory>
</VirtualHost>
"""


def test_docroots_in_config_reads_every_directive():
    assert docroots_in_config(CONFIG) == ["/home/juan/www/demo/public"]
    assert docroots_in_config('  documentroot "/home/juan/www/a b"\nDocumentRoot /x\n') == ["/home/juan/www/a b", "/x"]
    assert docroots_in_config("<VirtualHost *:80>\n</VirtualHost>\n") == []


@pytest.mark.parametrize("docroot", [
    "/home/juan/www/demo",
    "/home/juan/www/demo/public",
    "/home/juan/www/demo/web",
])
def test_docroot_inside_projects_dir_is_valid(docroot):
    assert docroot_location_error(docroot, PROJECTS) == ""


@pytest.mark.parametrize("docroot", [
    "/home/juan/www",
    "/home/juan/www/public",
    "/home/juan",
    "/var/www/html",
    "/home/juan/www/../Documentos/x",
])
def test_docroot_outside_projects_dir_is_rejected(docroot):
    assert "debe estar dentro de /home/juan/www" in docroot_location_error(docroot, PROJECTS)


def test_save_vhost_config_rejects_outside_docroot_without_writing(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no debería escribir la configuración")
    monkeypatch.setattr(vhosts, "_apply_apache_config", fail)

    ok, error = vhosts.save_vhost_config("demo", CONFIG.replace("/home/juan/www/demo/public", "/home/juan"), PROJECTS)

    assert not ok and "debe estar dentro" in error


def test_update_docroot_rejects_outside_docroot_without_writing(tmp_path, monkeypatch):
    conf = tmp_path / "demo.test.conf"
    conf.write_text(CONFIG)
    monkeypatch.setattr(vhosts, "vhost_config_path", lambda name: conf)

    def fail(*args, **kwargs):
        raise AssertionError("no debería escribir la configuración")
    monkeypatch.setattr(vhosts, "_apply_apache_config", fail)

    ok, error = vhosts.update_docroot("demo", str(tmp_path), PROJECTS)

    assert not ok and "debe estar dentro" in error
    assert conf.read_text() == CONFIG


def test_list_vhosts_outside(monkeypatch):
    docroots = {
        "dentro": "/home/juan/www/dentro/public",
        "fuera": "/home/juan/Documentos/fuera",
        "raiz": "/home/juan/www",
        "sin-docroot": "",
    }
    monkeypatch.setattr(vhosts, "list_projects", lambda: list(docroots))
    monkeypatch.setattr(vhosts, "get_docroot", lambda name: docroots[name])

    assert list_vhosts_outside(PROJECTS) == ["fuera", "raiz"]
