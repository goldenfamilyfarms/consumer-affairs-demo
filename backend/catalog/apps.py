from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"

    def ready(self):
        """Wire cache invalidation for the industry-slug lookup.

        Any Industry create/update/delete drops the cached slug set so
        ``validate_industry`` never validates against stale data.
        """
        from django.db.models.signals import post_delete, post_save

        from catalog.cache import clear_industry_slugs_cache
        from catalog.models import Industry

        post_save.connect(
            clear_industry_slugs_cache,
            sender=Industry,
            dispatch_uid="catalog.clear_industry_slugs_on_save",
        )
        post_delete.connect(
            clear_industry_slugs_cache,
            sender=Industry,
            dispatch_uid="catalog.clear_industry_slugs_on_delete",
        )
