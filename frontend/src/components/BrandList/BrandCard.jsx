/**
 * BrandCard — presentational card for a single brand row (Requirements 12.3,
 * 12.9). Renders as a semantic `<article>` with a heading that links to the
 * brand detail page and an accessible star-rating value.
 *
 * The card data shape matches `BrandCard` from `../../api/brands.js`:
 *   { name, slug, industry, average_rating, review_count,
 *     short_description, top_review_snippet }
 *
 * @typedef {import("../../api/brands.js").BrandCard} BrandCardData
 */

import VisuallyHidden from "./VisuallyHidden.jsx";

const MAX_STARS = 5;

/**
 * Accessible star-rating display (Req 12.9). The visual glyphs are decorative
 * (`aria-hidden`); the numeric value is exposed both visibly (`.rating-value`)
 * and, for a self-describing label, via `aria-label` on the container plus
 * visually-hidden text.
 *
 * @param {{ rating: number | null }} props
 */
function StarRating({ rating }) {
  if (rating == null) {
    // Zero-review brands carry a null rating (Req 10.7). Surface that as text.
    return (
      <div className="stars" aria-label="No ratings yet">
        <span className="rating-value" aria-hidden="true">
          No ratings yet
        </span>
      </div>
    );
  }

  const filled = Math.round(rating);
  const display = rating.toFixed(1);
  const label = `Average rating: ${display} out of ${MAX_STARS}`;

  return (
    <div className="stars" aria-label={label}>
      {Array.from({ length: MAX_STARS }, (_, index) => (
        <span
          key={index}
          className={index < filled ? "star-full" : "star-empty"}
          aria-hidden="true"
        >
          {"\u2605"}
        </span>
      ))}
      <span className="rating-value" aria-hidden="true">
        {display}
      </span>
      <VisuallyHidden>{label}</VisuallyHidden>
    </div>
  );
}

/**
 * Render a single brand as a semantic card.
 *
 * @param {{ brand: BrandCardData }} props
 */
export default function BrandCard({ brand }) {
  const {
    name,
    slug,
    industry,
    average_rating: averageRating,
    review_count: reviewCount,
    short_description: shortDescription,
    top_review_snippet: topReviewSnippet,
  } = brand;

  const excerpt = shortDescription || topReviewSnippet;

  return (
    <article className="card card--interactive">
      <h3>
        <a href={`/brand/${slug}/`}>{name}</a>
      </h3>

      {industry ? <span className="badge">{industry}</span> : null}

      <StarRating rating={averageRating == null ? null : Number(averageRating)} />

      <div className="meta">
        {reviewCount} {reviewCount === 1 ? "review" : "reviews"}
      </div>

      {excerpt ? <p className="excerpt">{excerpt}</p> : null}
    </article>
  );
}
