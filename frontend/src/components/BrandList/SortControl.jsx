/**
 * SortControl — a single labelled native `<select>` that combines the sort key
 * and direction into one clear choice (Requirements 12.7, 12.9, 12.10).
 *
 * Collapsing key + direction into one control removes the awkward "pick a key,
 * then a separate direction" two-step: each option reads as an intent
 * ("Highest rated") rather than requiring the user to reason about ascending
 * vs descending. The control is a native `<select>` with an associated
 * `<label>`, so it stays semantic and keyboard-operable.
 *
 * Each option maps to the Brand_API contract (see `../../api/brands.js`):
 *   sort: "" (API default) | "avg_rating" | "review_count"
 *   dir:  "" (API default) | "desc" | "asc"
 */

/** Option value = `"<sort>:<dir>"`, or "" for the API default order. */
const SORT_OPTIONS = [
  { value: "", label: "Relevance", sort: "", dir: "" },
  { value: "avg_rating:desc", label: "Highest rated", sort: "avg_rating", dir: "desc" },
  { value: "avg_rating:asc", label: "Lowest rated", sort: "avg_rating", dir: "asc" },
  { value: "review_count:desc", label: "Most reviewed", sort: "review_count", dir: "desc" },
  { value: "review_count:asc", label: "Fewest reviewed", sort: "review_count", dir: "asc" },
];

/** Derive the current option value from the active sort/dir filters. */
function currentValue(sort, dir) {
  if (!sort) return "";
  return `${sort}:${dir || "desc"}`;
}

/**
 * @param {{
 *   sort: string,
 *   dir: string,
 *   onChange: (next: { sort: string, dir: string }) => void,
 *   id?: string,
 * }} props
 */
export default function SortControl({ sort, dir, onChange, id = "brand-sort" }) {
  const value = currentValue(sort, dir);

  const handleChange = (event) => {
    const option =
      SORT_OPTIONS.find((opt) => opt.value === event.target.value) ||
      SORT_OPTIONS[0];
    onChange({ sort: option.sort, dir: option.dir });
  };

  return (
    <div className="control">
      <label htmlFor={id}>Sort by</label>
      <select id={id} name="sort" value={value} onChange={handleChange}>
        {SORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
