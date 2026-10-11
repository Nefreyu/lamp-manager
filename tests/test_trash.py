import json
import shutil
from pathlib import Path

import pytest

import services.vhosts as vhosts
from services.systemd import is_clearable_log

NAME = "zz-lm-test"


@pytest.fixture
def system(tmp_path, monkeypatch):
    """Sistema simulado: las llamadas con sudo se aplican sobre carpetas temporales."""
    projects = tmp_path / "www"
    projects.mkdir()
    sites = tmp_path / "sites-available"
    sites.mkdir()
    sudo_calls: list[list[str]] = []
    state = {"docroot": str(projects / NAME)}

    def fake_sudo(cmd: list[str]) -> bool:
        sudo_calls.append(cmd)
        if cmd[0] == "mv":
            shutil.move(cmd[1], cmd[2])
        elif cmd[:2] == ["rm", "-rf"]:
            shutil.rmtree(cmd[2], ignore_errors=True)
        return True

    def fake_write(dest: str, content: str) -> bool:
        Path(dest).write_text(content)
        return True

    monkeypatch.setattr(vhosts, "TRASH_DIR", tmp_path / "trash")
    monkeypatch.setattr(vhosts, "CERTS_DIR", tmp_path / "certs")
    monkeypatch.setattr(vhosts, "APACHE_SITES_AVAILABLE", sites)
    monkeypatch.setattr(vhosts, "get_docroot", lambda name: state["docroot"])
    monkeypatch.setattr(vhosts, "_run_sudo", fake_sudo)
    monkeypatch.setattr(vhosts, "_run_sudo_output", lambda cmd: None)
    monkeypatch.setattr(vhosts, "_sudo_write_file", fake_write)
    monkeypatch.setattr(vhosts, "add_hosts_entry", lambda domain: True)
    monkeypatch.setattr(vhosts, "remove_hosts_entry", lambda domain: True)
    monkeypatch.setattr(vhosts, "database_exists", lambda name: False)
    monkeypatch.setattr(vhosts, "is_command_installed", lambda cmd: False)
    monkeypatch.setattr(vhosts, "generate_index_page", lambda: True)
    for fn in ("disable_site", "remove_vhost_config", "reload", "enable_site", "write_vhost_config"):
        monkeypatch.setattr(vhosts.nginx, fn, lambda *a, **k: True)
    monkeypatch.setattr(vhosts.nginx, "vhost_config_path", lambda name: tmp_path / f"nginx-{name}.conf")

    return {"projects": projects, "sites": sites, "sudo": sudo_calls, "state": state, "tmp": tmp_path}


def trashed_meta(system) -> dict:
    (item,) = (system["tmp"] / "trash").iterdir()
    return json.loads((item / "meta.json").read_text())


def test_is_inside_projects_dir(tmp_path):
    base = tmp_path / "www"
    (base / "app" / "public").mkdir(parents=True)
    assert vhosts.is_inside_projects_dir(base / "app", str(base))
    assert vhosts.is_inside_projects_dir(base / "app" / "public", str(base))
    assert not vhosts.is_inside_projects_dir(base, str(base))
    assert not vhosts.is_inside_projects_dir(tmp_path, str(base))
    assert not vhosts.is_inside_projects_dir(base / ".." / "otro", str(base))
    assert not vhosts.is_inside_projects_dir(None, str(base))


def test_trash_moves_project_folder_inside_projects_dir(system):
    project = system["projects"] / NAME
    project.mkdir()

    ok, warning = vhosts.trash_vhost(NAME, str(system["projects"]))

    assert ok and warning == ""
    assert not project.exists()
    assert trashed_meta(system)["files_moved"] is True


@pytest.mark.parametrize("docroot_key", ["projects_dir", "outside"])
def test_trash_keeps_folder_when_docroot_is_unsafe(system, docroot_key):
    outside = system["tmp"] / "documentos"
    outside.mkdir()
    (system["projects"] / "otro-proyecto").mkdir()
    unsafe = {"projects_dir": system["projects"], "outside": outside}[docroot_key]
    system["state"]["docroot"] = str(unsafe)

    ok, warning = vhosts.trash_vhost(NAME, str(system["projects"]))

    assert ok and "no se ha movido" in warning
    assert unsafe.is_dir()
    assert (system["projects"] / "otro-proyecto").is_dir()
    assert not any(cmd[0] == "mv" and cmd[1] == str(unsafe) for cmd in system["sudo"])
    assert trashed_meta(system)["files_moved"] is False


def test_restore_returns_files_and_fixes_permissions(system):
    project = system["projects"] / NAME
    project.mkdir()
    vhosts.trash_vhost(NAME, str(system["projects"]))
    trash_id = trashed_meta(system)["trash_id"]
    system["sudo"].clear()

    ok, error = vhosts.restore_vhost(trash_id, str(system["projects"]))

    assert ok and error == ""
    assert project.is_dir()
    assert any(cmd[:2] == ["chown", "-R"] for cmd in system["sudo"])


def test_restore_without_files_never_changes_owner(system):
    outside = system["tmp"] / "documentos"
    outside.mkdir()
    system["state"]["docroot"] = str(outside)
    vhosts.trash_vhost(NAME, str(system["projects"]))
    trash_id = trashed_meta(system)["trash_id"]
    system["sudo"].clear()

    ok, _ = vhosts.restore_vhost(trash_id, str(system["projects"]))

    assert ok
    assert not any(cmd[0] in ("chown", "chmod", "find") for cmd in system["sudo"])


def test_restore_refuses_when_vhost_already_exists(system):
    (system["projects"] / NAME).mkdir()
    vhosts.trash_vhost(NAME, str(system["projects"]))
    trash_id = trashed_meta(system)["trash_id"]
    (system["sites"] / f"{NAME}.test.conf").write_text("nuevo")

    ok, error = vhosts.restore_vhost(trash_id, str(system["projects"]))

    assert not ok and "Ya existe un vhost" in error
    assert (system["sites"] / f"{NAME}.test.conf").read_text() == "nuevo"


def test_restore_refuses_when_folder_already_exists(system):
    project = system["projects"] / NAME
    project.mkdir()
    vhosts.trash_vhost(NAME, str(system["projects"]))
    trash_id = trashed_meta(system)["trash_id"]
    project.mkdir()

    ok, error = vhosts.restore_vhost(trash_id, str(system["projects"]))

    assert not ok and "Ya existe la carpeta" in error


def test_restore_old_item_without_project_dir_uses_projects_dir(system):
    item = system["tmp"] / "trash" / "viejo"
    (item / "files").mkdir(parents=True)
    (item / "meta.json").write_text(json.dumps({"trash_id": "viejo", "name": NAME, "project_dir": None}))

    ok, error = vhosts.restore_vhost("viejo", str(system["projects"]))

    assert ok, error
    assert (system["projects"] / NAME).is_dir()


@pytest.mark.parametrize("path, allowed", [
    ("/var/log/apache2/enigma-php.test-error.log", True),
    ("/var/log/nginx/access.log", True),
    ("/var/log/mysql/error.log", True),
    ("/var/log/php8.5-fpm.log", True),
    ("/var/log/apache2", False),
    ("/var/log/apache2/../../../etc/passwd", False),
    ("/etc/passwd", False),
    ("/var/log/syslog", False),
    ("/var/log/php-fpm.log.bak", False),
])
def test_is_clearable_log(path, allowed):
    assert is_clearable_log(path) is allowed
