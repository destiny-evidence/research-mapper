/**
 * Model-authored prose.
 */
export function Reasoning({ text }) {
  if (!text) return null;
  return (
    <div class="reasoning">
      <div class="reasoning-head lab">Model reasoning</div>
      <div class="reasoning-text">{text}</div>
    </div>
  );
}
