"""Root URL configuration.

Wires the catalog (server-rendered pages) and api (REST endpoints) apps.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("catalog.urls")),
]
