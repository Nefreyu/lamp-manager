import pytest

import services.watcher as watcher


@pytest.fixture
def statuses(monkeypatch) -> dict[str, bool]:
    current = {"apache2": True, "nginx": True}
    monkeypatch.setattr(watcher, "_read_service_statuses", lambda: dict(current))
    return current


@pytest.fixture
def project_watcher(statuses, monkeypatch) -> tuple[watcher.ProjectWatcher, list[bool]]:
    regens: list[bool] = []
    w = watcher.ProjectWatcher()
    w._service_statuses = dict(statuses)
    monkeypatch.setattr(w, "_schedule_regen", lambda: regens.append(True))
    return w, regens


def test_check_services_regenerates_when_a_service_stops(project_watcher, statuses):
    w, regens = project_watcher
    statuses["nginx"] = False

    w.check_services()

    assert regens == [True]


def test_check_services_does_nothing_without_changes(project_watcher):
    w, regens = project_watcher

    w.check_services()

    assert regens == []


def test_check_services_regenerates_once_per_change(project_watcher, statuses):
    w, regens = project_watcher
    statuses["nginx"] = False

    w.check_services()
    w.check_services()

    assert regens == [True]
