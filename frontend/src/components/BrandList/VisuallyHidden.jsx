/**
 * Renders text that is visually hidden but available to assistive technology.
 *
 * Used to expose accessible label text (e.g. star-rating values) without
 * relying on a SCSS utility class, keeping these components self-contained.
 */

// Standard "visually hidden" recipe: clip the element to a 1px box, off-screen,
// so it stays in the accessibility tree while being visually removed.
const VISUALLY_HIDDEN_STYLE = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

export default function VisuallyHidden({ children }) {
  return <span style={VISUALLY_HIDDEN_STYLE}>{children}</span>;
}
