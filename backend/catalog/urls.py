"""URL patterns for server-rendered catalog pages.

Slug-based routes matching the WordPress permalink structure so existing
inbound links continue to resolve (Requirements 9.3, 9.4).
"""

from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("brand/<slug:slug>/", views.brand_detail, name="brand_detail"),
    path("review/<slug:slug>/", views.review_detail, name="review_detail"),
]
