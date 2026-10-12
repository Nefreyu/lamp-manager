import shutil
import subprocess

import pytest

from services.vhosts import INDEX_BASIC_TEMPLATE, scaffold_project

PHP_BASIC = {"id": "php", "label": "PHP básico"}


def test_php_basic_creates_initial_index(tmp_path):
    ok, error = scaffold_project(PHP_BASIC, "demo", str(tmp_path))

    index = tmp_path / "demo" / "index.php"
    assert ok and error is None
    assert index.read_text(encoding="utf-8") == INDEX_BASIC_TEMPLATE.read_text(encoding="utf-8")


def test_php_basic_keeps_existing_index(tmp_path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "index.html").write_text("mío")

    ok, _ = scaffold_project(PHP_BASIC, "demo", str(tmp_path))

    assert ok
    assert not (project / "index.php").exists()
    assert (project / "index.html").read_text() == "mío"


@pytest.mark.skipif(shutil.which("php") is None, reason="php no está instalado")
def test_index_basic_template_is_valid_php():
    result = subprocess.run(["php", "-l", str(INDEX_BASIC_TEMPLATE)], capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
