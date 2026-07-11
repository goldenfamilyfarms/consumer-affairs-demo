"""URL patterns for the REST API.

Wires ``GET /api/brands/`` to the brand listing view (Req 10.1).
"""

from django.urls import path

from api.views import BrandListView, IndustryListView

app_name = "api"

urlpatterns = [
    path("brands/", BrandListView.as_view(), name="brand-list"),
    path("industries/", IndustryListView.as_view(), name="industry-list"),
]
