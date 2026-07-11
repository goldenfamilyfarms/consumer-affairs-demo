"""Root URL configuration.

Wires the catalog (server-rendered pages) and api (REST endpoints) apps.
"""

from django.contrib import admin
from django.urls import include, path

from api.api import api as ninja_api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", ninja_api.urls),
    path("", include("catalog.urls")),
]
