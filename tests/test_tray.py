from services.tray import ICON_ERROR, ICON_OK, ICON_WARNING, icon_for_statuses

ALL_ACTIVE = {"apache2": True, "nginx": True, "mysql": True, "php8.4-fpm": True, "mailpit": True}


def with_stopped(*service_ids: str) -> dict[str, bool]:
    return {sid: active and sid not in service_ids for sid, active in ALL_ACTIVE.items()}


def test_all_services_active_is_ok():
    assert icon_for_statuses(ALL_ACTIVE) == ICON_OK


def test_only_apache_as_web_server_is_ok():
    assert icon_for_statuses(with_stopped("nginx")) == ICON_OK


def test_only_nginx_as_web_server_is_ok():
    assert icon_for_statuses(with_stopped("apache2")) == ICON_OK


def test_no_web_server_active_is_error():
    assert icon_for_statuses(with_stopped("apache2", "nginx")) == ICON_ERROR


def test_php_fpm_stopped_is_warning():
    assert icon_for_statuses(with_stopped("php8.4-fpm")) == ICON_WARNING


def test_mysql_stopped_is_warning():
    assert icon_for_statuses(with_stopped("mysql")) == ICON_WARNING


def test_mailpit_stopped_is_ok():
    assert icon_for_statuses(with_stopped("mailpit")) == ICON_OK


def test_nginx_not_installed_is_ok_with_apache():
    statuses = {sid: active for sid, active in ALL_ACTIVE.items() if sid != "nginx"}

    assert icon_for_statuses(statuses) == ICON_OK
