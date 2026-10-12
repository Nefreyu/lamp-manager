import pytest

import services.systemd as systemd
import services.vhosts as vhosts

EVIL_BRANCH = "<script>alert('rama')</script>"
EVIL_DOCROOT = '/home/juan/www/demo"><img src=x onerror=alert(1)>'


def render(tmp_path, monkeypatch, nginx_active: bool = False) -> str:
    """Genera el dashboard con datos maliciosos y devuelve el HTML que se escribiría."""
    written: dict[str, str] = {}
    monkeypatch.setattr(vhosts, "INDEX_PAGE", tmp_path / "index.html")
    monkeypatch.setattr(vhosts, "INDEX_BACKUP", tmp_path / "index.html.bak")
    monkeypatch.setattr(vhosts, "list_projects", lambda: ["demo"])
    monkeypatch.setattr(vhosts, "vhost_is_enabled", lambda name: True)
    monkeypatch.setattr(vhosts, "get_docroot", lambda name: EVIL_DOCROOT)
    monkeypatch.setattr(vhosts, "vhost_has_https", lambda name: False)
    monkeypatch.setattr(vhosts, "get_git_branch", lambda path: EVIL_BRANCH)
    monkeypatch.setattr(vhosts, "get_project_size", lambda path: "<b>12M</b>")
    monkeypatch.setattr(vhosts, "get_project_last_modified", lambda path: "hace 1h")
    monkeypatch.setattr(vhosts, "get_recent_error_count", lambda name: 0)
    monkeypatch.setattr(vhosts, "database_exists", lambda name: False)
    monkeypatch.setattr(vhosts, "_run_sudo", lambda cmd: True)
    monkeypatch.setattr(vhosts, "_sudo_write_file", lambda dest, content: written.setdefault("html", content) or True)
    monkeypatch.setattr(systemd, "is_installed", lambda svc: False)
    monkeypatch.setattr(vhosts.apache, "get_http_port", lambda: 80)
    monkeypatch.setattr(vhosts.nginx, "get_http_port", lambda: 8080)
    monkeypatch.setattr(vhosts, "get_status", lambda service_id: service_id == "nginx" and nginx_active)

    assert vhosts.generate_index_page()
    return written["html"]


@pytest.fixture
def rendered(tmp_path, monkeypatch) -> str:
    return render(tmp_path, monkeypatch)


def test_dashboard_escapes_git_branch(rendered):
    assert EVIL_BRANCH not in rendered
    assert "&lt;script&gt;alert(&#x27;rama&#x27;)&lt;/script&gt;" in rendered


def test_dashboard_escapes_docroot(rendered):
    assert "<img src=x" not in rendered
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in rendered


def test_dashboard_escapes_project_size(rendered):
    assert "<b>12M</b>" not in rendered
    assert "&lt;b&gt;12M&lt;/b&gt;" in rendered


def test_dashboard_keeps_its_own_markup(rendered):
    assert '<span class="card-name">demo</span>' in rendered
    assert 'href="http://demo.test"' in rendered


def test_dashboard_shows_nginx_link_when_nginx_is_active(tmp_path, monkeypatch):
    html = render(tmp_path, monkeypatch, nginx_active=True)

    assert 'href="http://demo.test:8080"' in html


def test_dashboard_hides_nginx_link_when_nginx_is_stopped(tmp_path, monkeypatch):
    html = render(tmp_path, monkeypatch, nginx_active=False)

    assert "demo.test:8080" not in html
