import { diffChoice } from '../../derive.js'

const key = (item) => item.query

export function Queries({ payload, suggested }) {
  const { removed } = diffChoice(suggested?.queries, payload.queries, key)
  return (
    <>
      <div>
        {payload.queries.map((item) => (
          <div class="mono" key={item.query} style="font-size: 12px; color: var(--ink); padding: 9px 0; border-bottom: 1px solid var(--hair); line-height: 1.5;">
            {item.query}
          </div>
        ))}
        {removed.map((item) => (
          <div key={item.query} style="display: flex; align-items: baseline; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--hair);">
            <span class="mono" style="font-size: 12px; color: var(--faint); text-decoration: line-through;">{item.query}</span>
            <span class="lab">you removed</span>
          </div>
        ))}
      </div>
    </>
  )
}
