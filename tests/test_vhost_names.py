import pytest

import services.vhosts as vhosts
from services.vhosts import is_valid_vhost_name, register_orphan


@pytest.mark.parametrize("name", [
    "demo", "symfony-demo", "CalendarioDeTareas", "JolpicaF1", "a", "x" * 63,
])
def test_valid_names(name):
    assert is_valid_vhost_name(name)


@pytest.mark.parametrize("name", [
    "", "Mi Proyecto", "my_app", "-demo", "demo-", "demo.test", "café", "x" * 64, "../etc",
])
def test_invalid_names(name):
    assert not is_valid_vhost_name(name)


@pytest.fixture
def fake_system(tmp_path, monkeypatch):
    """Directorio de proyectos y sites-available falsos; create_vhost no toca el sistema."""
    projects = tmp_path / "www"
    projects.mkdir()
    sites = tmp_path / "sites-available"
    sites.mkdir()
    monkeypatch.setattr(vhosts, "APACHE_SITES_AVAILABLE", sites)
    created = []
    monkeypatch.setattr(vhosts, "create_vhost", lambda name, _dir: created.append(name) or True)
    return projects, sites, created


def test_register_orphan_with_valid_name_keeps_folder(fake_system):
    projects, _, created = fake_system
    (projects / "MiProyecto").mkdir()

    assert register_orphan(str(projects), "MiProyecto") == (True, "MiProyecto", "")
    assert (projects / "MiProyecto").is_dir()
    assert created == ["MiProyecto"]


def test_register_orphan_renames_invalid_folder_to_slug(fake_system):
    projects, _, created = fake_system
    (projects / "Mi Proyecto").mkdir()

    assert register_orphan(str(projects), "Mi Proyecto") == (True, "mi-proyecto", "")
    assert (projects / "mi-proyecto").is_dir()
    assert not (projects / "Mi Proyecto").exists()
    assert created == ["mi-proyecto"]


def test_register_orphan_refuses_existing_target_folder(fake_system):
    projects, _, created = fake_system
    (projects / "Mi Proyecto").mkdir()
    (projects / "mi-proyecto").mkdir()

    ok, _, error = register_orphan(str(projects), "Mi Proyecto")
    assert not ok and "Ya existe la carpeta" in error
    assert (projects / "Mi Proyecto").is_dir()
    assert created == []


def test_register_orphan_refuses_existing_vhost(fake_system):
    projects, sites, created = fake_system
    (projects / "Mi Proyecto").mkdir()
    (sites / "mi-proyecto.test.conf").write_text("")

    ok, _, error = register_orphan(str(projects), "Mi Proyecto")
    assert not ok and "Ya existe un vhost" in error
    assert (projects / "Mi Proyecto").is_dir()
    assert created == []


def test_register_orphan_without_possible_slug(fake_system):
    projects, _, created = fake_system
    (projects / "___").mkdir()

    ok, name, _ = register_orphan(str(projects), "___")
    assert not ok and name == ""
    assert created == []


def test_create_vhost_rejects_invalid_name_before_touching_system(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no debería escribir nada")
    monkeypatch.setattr(vhosts, "_sudo_write_file", fail)
    monkeypatch.setattr(vhosts, "_run_sudo", fail)

    assert vhosts.create_vhost("Mi Proyecto", "/home/juan/www") is False
