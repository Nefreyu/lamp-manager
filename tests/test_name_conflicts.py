import pytest

import services.vhosts as vhosts
from services.vhosts import find_folder_conflict, find_vhost_conflict, register_orphan


@pytest.fixture
def sites(tmp_path, monkeypatch):
    sites = tmp_path / "sites-available"
    sites.mkdir()
    for name in ("GlobeTestClaude", "symfony-demo"):
        (sites / f"{name}.test.conf").write_text("")
    monkeypatch.setattr(vhosts, "APACHE_SITES_AVAILABLE", sites)
    return sites


def test_find_vhost_conflict_ignores_case(sites):
    assert find_vhost_conflict("globetestclaude") == "GlobeTestClaude"
    assert find_vhost_conflict("GLOBETESTCLAUDE") == "GlobeTestClaude"
    assert find_vhost_conflict("symfony-demo") == "symfony-demo"
    assert find_vhost_conflict("demo") is None


def test_find_vhost_conflict_can_exclude_itself(sites):
    assert find_vhost_conflict("GlobeTestClaude", exclude="GlobeTestClaude") is None
    assert find_vhost_conflict("globetestclaude", exclude="globetestclaude") == "GlobeTestClaude"


def test_find_folder_conflict_ignores_case(tmp_path):
    (tmp_path / "GlobeTestClaude").mkdir()
    assert find_folder_conflict(tmp_path, "globetestclaude") == tmp_path / "GlobeTestClaude"
    assert find_folder_conflict(tmp_path, "GlobeTestClaude", exclude="GlobeTestClaude") is None
    assert find_folder_conflict(tmp_path, "otro") is None
    assert find_folder_conflict(tmp_path / "no-existe", "x") is None


def test_create_vhost_rejects_name_differing_only_in_case(sites, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no debería tocar el sistema")
    monkeypatch.setattr(vhosts, "_sudo_write_file", fail)
    monkeypatch.setattr(vhosts, "_run_sudo", fail)

    assert vhosts.create_vhost("globetestclaude", "/home/juan/www") is False


def test_register_orphan_rejects_folder_clashing_with_existing_vhost(sites, tmp_path, monkeypatch):
    projects = tmp_path / "www"
    (projects / "globetestclaude").mkdir(parents=True)
    monkeypatch.setattr(vhosts, "create_vhost", lambda *a: pytest.fail("no debería crear el vhost"))

    ok, _, error = register_orphan(str(projects), "globetestclaude")

    assert not ok and "GlobeTestClaude" in error


def test_register_orphan_rejects_slug_clashing_with_folder_in_other_case(sites, tmp_path, monkeypatch):
    projects = tmp_path / "www"
    (projects / "Mi Proyecto").mkdir(parents=True)
    (projects / "Mi-Proyecto").mkdir()
    monkeypatch.setattr(vhosts, "create_vhost", lambda *a: pytest.fail("no debería crear el vhost"))

    ok, _, error = register_orphan(str(projects), "Mi Proyecto")

    assert not ok and "Ya existe la carpeta" in error
    assert (projects / "Mi Proyecto").is_dir()
