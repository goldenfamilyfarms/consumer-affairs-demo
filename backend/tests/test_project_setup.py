"""Smoke tests verifying the project scaffolding is wired correctly.

These confirm that pytest-django can collect and run tests, that the local
apps are installed, and that the root URLConf is registered.
"""

from django.apps import apps
from django.conf import settings


def test_local_apps_installed():
    assert "catalog" in settings.INSTALLED_APPS
    assert "api" in settings.INSTALLED_APPS
    assert "rest_framework" in settings.INSTALLED_APPS


def test_apps_are_loaded():
    assert apps.is_installed("catalog")
    assert apps.is_installed("api")


def test_root_urlconf_registered():
    assert settings.ROOT_URLCONF == "config.urls"


def test_url_configuration_imports():
    from django.urls import get_resolver

    resolver = get_resolver()
    # url_patterns resolves lazily; accessing it validates the URLConf tree.
    assert resolver.url_patterns is not None
