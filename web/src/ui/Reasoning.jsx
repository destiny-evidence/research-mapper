/**
 * Model-authored prose. Always fenced and labelled: a reader must never have to
 * work out whether a sentence came from us or from an LLM.
 *
 * The label is a header on the box rather than a run-in to the text, so the
 * boundary of what the model wrote is unambiguous. Set in mono, which is this
 * UI's register for machine output, and deliberately not in the serif or in
 * quote marks — both read as a person being quoted, and a generated sentence
 * has no speaker to attribute it to.
 */
export function Reasoning({ text }) {
  if (!text) return null
  return (
    <div class="reasoning">
      <div class="reasoning-head lab">LLM reasoning</div>
      <div class="reasoning-text">{text}</div>
    </div>
  )
}
