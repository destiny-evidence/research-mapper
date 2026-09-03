/**
 * Model-authored prose.
 */
export function Reasoning({ text, label = "Model reasoning" }) {
  if (!text) return null;
  return (
    <div class="reasoning">
      <div class="reasoning-head lab">{label}</div>
      <div class="reasoning-text">{text}</div>
    </div>
  );
}
