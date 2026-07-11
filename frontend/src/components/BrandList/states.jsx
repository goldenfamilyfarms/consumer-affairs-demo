/**
 * Presentational state views for BrandList (Requirements 12.2, 12.4, 12.5).
 *
 * Each state renders inside a live region (`aria-live="polite"`, or
 * `role="alert"` for errors) so transitions are announced to assistive tech.
 */

import VisuallyHidden from "./VisuallyHidden.jsx";

/** A single shimmer skeleton card mirroring the real BrandCard footprint. */
function SkeletonCard() {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--badge" />
      <div className="skeleton skeleton--stars" />
      <div className="skeleton skeleton--line" />
      <div className="skeleton skeleton--line" />
      <div className="skeleton skeleton--line-short" />
    </div>
  );
}

/**
 * Loading state shown while a Brand_API request is in flight (Req 12.2).
 * Renders skeleton cards (no layout shift when data arrives) plus a
 * visually-hidden status message for assistive tech.
 *
 * @param {{ count?: number }} props
 */
export function Loading({ count = 6 }) {
  return (
    <div role="status" aria-live="polite">
      <VisuallyHidden>Loading brands…</VisuallyHidden>
      <div className="grid">
        {Array.from({ length: count }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  );
}

/**
 * Empty state shown when the API returns zero brand rows (Req 12.4).
 */
export function Empty() {
  return (
    <div className="brand-list__state" role="status" aria-live="polite">
      <p>No brands match the current filters.</p>
      <VisuallyHidden>Try clearing the industry filter.</VisuallyHidden>
    </div>
  );
}

/**
 * Error state shown when a Brand_API request fails (Req 12.5). Includes a
 * retry action that re-issues the request.
 *
 * @param {{ message?: string, onRetry: () => void }} props
 */
export function Error({ message, onRetry }) {
  return (
    <div
      className="brand-list__state brand-list__state--error"
      role="alert"
      aria-live="polite"
    >
      <p>{message || "Something went wrong while loading brands."}</p>
      <button type="button" className="btn" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
