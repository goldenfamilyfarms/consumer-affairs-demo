"""Server-rendered views for the catalog app.

Implements the homepage, brand detail, and review detail pages using
Django templates and the reference theme's class names.
"""

from django.shortcuts import get_object_or_404, render

from catalog.models import Brand, Review


def home(request):
    """Homepage: hero section, recent reviews (date-desc), featured brands.

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """
    recent_reviews = Review.objects.select_related("brand").order_by("-wp_post_date")[:10]
    featured_brands = Brand.objects.with_stats().select_related("industry")[:5]

    return render(request, "catalog/home.html", {
        "recent_reviews": recent_reviews,
        "featured_brands": featured_brands,
    })


def brand_detail(request, slug):
    """Brand detail page at /brand/<slug>/.

    Requirements: 7.1, 7.2, 7.3, 7.4, 9.3
    """
    brand = get_object_or_404(
        Brand.objects.with_stats().select_related("industry"),
        slug=slug,
    )
    reviews = brand.reviews.select_related("reviewer").order_by("-wp_post_date")

    return render(request, "catalog/brand_detail.html", {
        "brand": brand,
        "reviews": reviews,
    })


def review_detail(request, slug):
    """Review detail page at /review/<slug>/.

    Requirements: 8.1, 8.2, 8.3, 8.4, 9.4
    """
    review = get_object_or_404(
        Review.objects.select_related("brand"),
        slug=slug,
    )

    return render(request, "catalog/review_detail.html", {
        "review": review,
    })
