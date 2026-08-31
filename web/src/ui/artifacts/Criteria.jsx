import { diffChoice } from '../../derive.js'

const key = (item) => `${item.criterion_type}:${item.description}`

function Column({ title, items, added, removed }) {
  return (
    <div>
      <div class="lab" style="color: #3d3b36; padding-bottom: 7px; border-bottom: 1px solid var(--line);">{title}</div>
      {items.map((item) => (
        <div key={key(item)} style="display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--hair);">
          <span style="font-size: 12.5px; color: var(--ink); line-height: 1.5; flex-grow: 1;">{item.description}</span>
          {added.some((other) => key(other) === key(item)) ? <span class="lab" style="color: var(--amber);">you added</span> : null}
        </div>
      ))}
      {removed.map((item) => (
        <div key={key(item)} style="display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--hair);">
          <span style="font-size: 12.5px; color: var(--faint); line-height: 1.5; flex-grow: 1; text-decoration: line-through;">{item.description}</span>
          <span class="lab">you removed</span>
        </div>
      ))}
    </div>
  )
}

export function Criteria({ payload, suggested }) {
  const { added, removed } = diffChoice(suggested?.criteria, payload.criteria, key)
  const of = (type, list) => list.filter((item) => item.criterion_type === type)
  return (
    <>
      <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 26px;">
        <Column
          title="Inclusion"
          items={of('inclusion', payload.criteria)}
          added={added}
          removed={of('inclusion', removed)}
        />
        <Column
          title="Exclusion"
          items={of('exclusion', payload.criteria)}
          added={added}
          removed={of('exclusion', removed)}
        />
      </div>
    </>
  )
}
