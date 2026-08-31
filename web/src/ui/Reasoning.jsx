/**
 * Model-authored prose. Always boxed and labelled: a reader must never have to
 * work out whether a sentence came from us or from an LLM.
 */
export function Reasoning({ text }) {
  if (!text) return null
  return (
    <div class="reasoning">
      <span class="lab">LLM reasoning: </span>
      <q>{text}</q>
    </div>
  )
}
