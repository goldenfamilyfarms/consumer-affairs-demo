"""Admin registrations for catalog models.

Lightweight registrations so industries, brands, reviews, and reviewers are
manageable in a running app (e.g. adding an industry, which is PROTECT-guarded
against deletion while brands reference it).
"""

from django.contrib import admin

from catalog.models import Brand, ImportLedger, Industry, Review, Reviewer


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "wp_term_id")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Reviewer)
class ReviewerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "wp_user_login", "email", "wp_user_id")
    search_fields = ("display_name", "wp_user_login", "email")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "founded_year", "headquarters", "wp_post_id")
    list_filter = ("industry",)
    search_fields = ("name", "slug", "headquarters")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("industry",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "rating", "reviewer_name", "wp_post_date")
    list_filter = ("rating", "brand__industry")
    search_fields = ("title", "slug", "reviewer_name", "reviewer_location")
    autocomplete_fields = ("brand", "reviewer")
    date_hierarchy = "wp_post_date"


@admin.register(ImportLedger)
class ImportLedgerAdmin(admin.ModelAdmin):
    list_display = ("model_label", "wp_id")
    list_filter = ("model_label",)
    search_fields = ("wp_id",)
