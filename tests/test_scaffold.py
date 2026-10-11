from services.vhosts import scaffold_project

PHP_BASIC = {"id": "php", "label": "PHP básico"}


def test_php_basic_creates_initial_index(tmp_path):
    ok, error = scaffold_project(PHP_BASIC, "demo", str(tmp_path))

    index = tmp_path / "demo" / "index.php"
    assert ok and error is None
    assert index.read_text().startswith("<?php")
    assert "echo 'demo.test' . PHP_EOL;" in index.read_text()


def test_php_basic_keeps_existing_index(tmp_path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "index.html").write_text("mío")

    ok, _ = scaffold_project(PHP_BASIC, "demo", str(tmp_path))

    assert ok
    assert not (project / "index.php").exists()
    assert (project / "index.html").read_text() == "mío"
