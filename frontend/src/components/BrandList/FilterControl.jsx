/**
 * FilterControl — labelled native `<select>` for the industry filter
 * (Requirements 12.6, 12.9, 12.10). A native `<select>` with an associated
 * `<label>` is semantic and keyboard-operable by default.
 *
 * @typedef {{ value: string, label: string }} Option
 */

const ALL_INDUSTRIES = { value: "", label: "All industries" };

/**
 * @param {{
 *   value: string,
 *   options: Option[],
 *   onChange: (value: string) => void,
 *   id?: string,
 * }} props
 */
export default function FilterControl({
  value,
  options,
  onChange,
  id = "brand-filter-industry",
}) {
  return (
    <div className="control">
      <label htmlFor={id}>Industry</label>
      <select
        id={id}
        name="industry"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value={ALL_INDUSTRIES.value}>{ALL_INDUSTRIES.label}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
