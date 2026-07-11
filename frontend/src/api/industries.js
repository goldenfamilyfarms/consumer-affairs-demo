/**
 * Fetch wrapper for `GET /api/industries/` — the full set of industries used to
 * populate the filter dropdown independently of the current brand result set.
 *
 * Returns an array (the endpoint is unpaginated):
 *   [{ name: string, slug: string, brand_count: number }, ...]
 *
 * @typedef {Object} Industry
 * @property {string} name
 * @property {string} slug
 * @property {number} brand_count
 */

/** Base path of the industries endpoint. Relative so it stays same-origin. */
export const INDUSTRIES_ENDPOINT = "/api/industries/";

/**
 * @param {{ signal?: AbortSignal, baseUrl?: string, fetchFn?: typeof fetch }} [options]
 * @returns {Promise<Industry[]>}
 */
export async function fetchIndustries(options = {}) {
  const { signal, baseUrl = INDUSTRIES_ENDPOINT, fetchFn = fetch } = options;

  const response = await fetchFn(baseUrl, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Request to ${INDUSTRIES_ENDPOINT} failed: ${response.status}`);
  }

  const body = await response.json();
  return Array.isArray(body) ? body : [];
}
