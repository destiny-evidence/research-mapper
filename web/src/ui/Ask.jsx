import { useState } from 'preact/hooks'
import { Tick, Remove, Plus } from './Icons.jsx'

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const label = (option) => option.label ?? option.value?.name ?? JSON.stringify(option.value)

/**
 * One decision, answered on its own. `answer_decisions` accepts a subset and
 * only requeues once nothing is left open, so each question saves separately.
 */
export function Question({ decision, onAnswer, saving }) {
  const Body = decision.type === 'edit_list' ? EditList : SelectMany
  return (
    <div class="question">
      <div class="option-label" style="font-weight: 500; margin-top: 14px;">{decision.prompt}</div>
      <Body decision={decision} onAnswer={onAnswer} saving={saving} />
    </div>
  )
}

function SelectMany({ decision, onAnswer, saving }) {
  const [picked, setPicked] = useState([])
  const exclusive = decision.constraints?.exclusive ?? []
  const min = decision.constraints?.min ?? 0
  const max = decision.constraints?.max

  const toggle = (value) => {
    const on = picked.some((item) => same(item, value))
    if (on) return setPicked(picked.filter((item) => !same(item, value)))
    // An exclusive option cannot be combined with anything else, in either
    // direction — picking one clears the rest, and it clears itself.
    if (exclusive.some((item) => same(item, value))) return setPicked([value])
    const rest = picked.filter((item) => !exclusive.some((ex) => same(ex, item)))
    return setPicked([...rest, value])
  }

  const ready = picked.length >= min && (!max || picked.length <= max)
  return (
    <>
      <div class="options">
        {decision.options.map((option) => {
          const on = picked.some((item) => same(item, option.value))
          return (
            <button type="button" class={`option ${on ? 'on' : ''}`} key={option.id} onClick={() => toggle(option.value)}>
              <span class={`box ${on ? 'on' : ''}`}>{on ? <Tick colour="#fff" size={9} /> : null}</span>
              <span class="option-label">{label(option)}</span>
            </button>
          )
        })}
      </div>
      <div class="actions">
        <button class="btn" disabled={!ready || saving} onClick={() => onAnswer(picked)}>Answer</button>
        <span class="hint">{constraintHint(min, max)}</span>
      </div>
    </>
  )
}

const constraintHint = (min, max) => {
  if (max && min === max) return `pick ${min}`
  if (max) return `pick ${min} to ${max}`
  return min > 1 ? `pick at least ${min}` : 'pick one or more'
}

function EditList({ decision, onAnswer, saving }) {
  const [items, setItems] = useState(decision.options.map((option) => option.value))
  const [draft, setDraft] = useState({ name: '', description: '' })
  const allowNew = Boolean(decision.constraints?.allow_new)
  const min = decision.constraints?.min ?? 0

  // New entries take their shape from what is already there, so this keeps
  // working if the item model gains a field.
  const template = Object.fromEntries(Object.keys(items[0] ?? { name: '' }).map((key) => [key, '']))
  const add = () => {
    if (!draft.name.trim()) return
    setItems([...items, { ...template, ...draft, name: draft.name.trim() }])
    setDraft({ name: '', description: '' })
  }

  return (
    <>
      <div class="chips" style="margin-top: 10px;">
        {items.map((item, i) => (
          <span class="tag" key={i} style="display: flex; align-items: center; gap: 7px;">
            {item.name ?? JSON.stringify(item)}
            <button
              type="button"
              style="background: none; border: 0; padding: 0; display: flex;"
              aria-label={`remove ${item.name}`}
              onClick={() => setItems(items.filter((_, index) => index !== i))}
            >
              <Remove />
            </button>
          </span>
        ))}
      </div>
      {allowNew ? (
        <div class="actions" style="margin-top: 10px;">
          <input
            value={draft.name}
            placeholder="add one"
            onInput={(event) => setDraft({ ...draft, name: event.currentTarget.value })}
            class="field"
          />
          {'description' in template ? (
            <input
              value={draft.description}
              placeholder="what it covers"
              onInput={(event) => setDraft({ ...draft, description: event.currentTarget.value })}
              class="field grow"
            />
          ) : null}
          <button class="btn plain" type="button" onClick={add}><Plus /> add</button>
        </div>
      ) : null}
      <div class="actions">
        <button class="btn" disabled={items.length < min || saving} onClick={() => onAnswer(items)}>Save</button>
        <span class="hint">{items.length < min ? `at least ${min}` : ''}</span>
      </div>
    </>
  )
}
