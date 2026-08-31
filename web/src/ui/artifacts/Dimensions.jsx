import { Reasoning } from '../Reasoning.jsx'

const ROLE = ['Rows', 'Columns', 'Filter']

export function Dimensions({ payload }) {
  return (
    <>
      <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px;">
        {payload.dimensions.map((dimension, i) => (
          <div key={dimension.name}>
            <div style={`border-top: 2px solid ${i < 2 ? '#3d3b36' : '#b3b0a9'}; padding-top: 8px;`}>
              <div class="lab">{ROLE[i] ?? 'Dimension'}</div>
              <div style="font-size: 13.5px; color: var(--ink); font-weight: 500; margin-top: 4px;">{dimension.name}</div>
              <div style="font-size: 11.5px; color: var(--muted); margin-top: 4px; line-height: 1.5;">{dimension.description}</div>
            </div>
            <div style="margin-top: 9px;">
              {dimension.subtopics.map((subtopic) => (
                <div key={subtopic.name} style="font-size: 12.5px; color: var(--ink); padding: 7px 0; border-bottom: 1px solid var(--hair);">
                  {subtopic.name}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Reasoning text={payload.reasoning} />
    </>
  )
}
