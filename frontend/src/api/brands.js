/**
 * Typed fetch wrapper for the Django brand-listing endpoint `GET /api/brands/`.
 *
 * The endpoint returns a page-number paginated collection (Requirement 11.1):
 *
 *   {
 *     "count": 5,
 *     "next": "http://.../api/brands/?page=2&page_size=12" | null,
 *     "previous": "http://.../api/brands/?page=1&page_size=12" | null,
 *     "results": [BrandCard, ...]
 *   }
 *
 * Each BrandCard row (Requirement 10.2) has the shape:
 *
 *   {
 *     "name": string,
 *     "slug": string,
 *     "industry": string,
 *     "average_rating": number | null,
 *     "review_count": number,
 *     "short_description": string | null,
 *     "top_review_snippet": string | null
 *   }
 *
 * @typedef {Object} BrandCard
 * @property {string} name
 * @property {string} slug
 * @property {string} industry
 * @property {string} industry_slug
 * @property {number | null} average_rating
 * @property {number} review_count
 * @property {string | null} short_description
 * @property {string | null} top_review_snippet
 *
 * @typedef {Object} BrandPage
 * @property {number} count            Total number of matching brand rows.
 * @property {string | null} next      Absolute URL of the next page, or null.
 * @property {string | null} previous  Absolute URL of the previous page, or null.
 * @property {BrandCard[]} results     Brand rows for the requested page.
 *
 * @typedef {Object} BrandQuery
 * @property {string} [industry]  Industry slug filter.
 * @property {"avg_rating" | "review_count"} [sort]  Sort key.
 * @property {"asc" | "desc"} [dir]  Sort direction.
 * @property {number} [page]  1-based page number.
 * @property {number} [pageSize]  Rows per page (maps to `page_size`).
 */

/** Base path of the brand-listing endpoint. Relative so it stays same-origin. */
export const BRANDS_ENDPOINT = "/api/brands/";

/**
 * Error thrown when the API responds with a non-2xx status. Carries the HTTP
 * status and any `{ "detail": "..." }` message the API returned (Req 11.4/11.5).
 */
export class BrandApiError extends Error {
  /**
   * @param {string} message
   * @param {{ status?: number, detail?: string }} [options]
   */
  constructor(message, { status, detail } = {}) {
    super(message);
    this.name = "BrandApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Build the query string for the brand-listing endpoint from a typed query
 * object. Undefined/empty params are omitted so the API applies its defaults.
 *
 * @param {BrandQuery} [query]
 * @returns {string} A query string beginning with `?`, or an empty string.
 */
export function buildBrandsQuery(query = {}) {
  const { industry, sort, dir, page, pageSize } = query;
  const params = new URLSearchParams();

  if (industry) params.set("industry", industry);
  if (sort) params.set("sort", sort);
  if (dir) params.set("dir", dir);
  if (page != null) params.set("page", String(page));
  if (pageSize != null) params.set("page_size", String(pageSize));

  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Fetch a page of brand rows from `GET /api/brands/`.
 *
 * @param {BrandQuery} [query]  Filter/sort/pagination parameters.
 * @param {{ signal?: AbortSignal, baseUrl?: string, fetchFn?: typeof fetch }} [options]
 *   Optional AbortSignal (for cancelable requests), base URL override, and a
 *   fetch implementation override (used by tests).
 * @returns {Promise<BrandPage>} The paginated brand collection.
 * @throws {BrandApiError} When the response status is not 2xx.
 */
export async function fetchBrands(query = {}, options = {}) {
  const {
    signal,
    baseUrl = BRANDS_ENDPOINT,
    fetchFn = fetch,
  } = options;

  const url = `${baseUrl}${buildBrandsQuery(query)}`;

  let response;
  try {
    response = await fetchFn(url, {
      signal,
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    // Network failure / aborted request. Re-throw AbortError untouched so
    // callers can distinguish cancellation from real failures.
    if (cause && cause.name === "AbortError") throw cause;
    throw new BrandApiError("Network request to /api/brands/ failed", {
      detail: cause instanceof Error ? cause.message : String(cause),
    });
  }

  if (!response.ok) {
    let detail;
    try {
      const body = await response.json();
      detail = body && typeof body.detail === "string" ? body.detail : undefined;
    } catch {
      detail = undefined;
    }
    throw new BrandApiError(
      detail || `Request to /api/brands/ failed with status ${response.status}`,
      { status: response.status, detail },
    );
  }

  return /** @type {Promise<BrandPage>} */ (response.json());
}
