import { useState } from 'preact/hooks'
import { buildGrid } from '../derive.js'

// Area carries the count, so the diameter goes as its square root.
const diameter = (n) => Math.round(13.9 * Math.sqrt(n))

const Bubble = ({ n }) => {
  const size = diameter(n)
  return (
    <span class="bubble" style={`width: ${size}px; height: ${size}px; font-size: ${size >= 46 ? 13 : size >= 40 ? 12 : size >= 34 ? 11.5 : 10.5}px;`}>
      {n}
    </span>
  )
}

export function EvidenceMap({ map, included }) {
  const [facet, setFacet] = useState(null)
  const grid = buildGrid(map, facet)
  if (!grid) return <div class="note">No map yet.</div>

  const unplaced = included == null ? null : included - (buildGrid(map, null)?.placed ?? 0)
  return (
    <>
      <div class="map-head">
        <div class="grow">
          <div class="map-title">{grid.rowDim.name} by {grid.colDim.name.toLowerCase()}</div>
          <div style="font-size: 12px; color: var(--muted); margin-top: 5px;">
            {grid.placed} placed{unplaced != null && unplaced > 0 ? `. ${unplaced} could not be placed.` : '.'}
          </div>
        </div>
        <div class="facets">
          <button type="button" class={`facet ${facet ? '' : 'on'}`} onClick={() => setFacet(null)}>All</button>
          {grid.facets.map((option) => (
            <button
              type="button"
              key={option.name}
              class={`facet ${facet === option.name ? 'on' : ''}`}
              onClick={() => setFacet(facet === option.name ? null : option.name)}
            >
              {option.name} {option.count}
            </button>
          ))}
        </div>
      </div>

      <div class="grid" style={`grid-template-columns: 200px repeat(${grid.cols.length}, minmax(0, 1fr));`}>
        <div />
        {grid.cols.map((col) => <div class="col-head lab" key={col}>{col}</div>)}
        {grid.rows.map((row, r) => {
          const empty = grid.cells[r].every((n) => n === 0)
          return [
            <div class="row-head" key={row} style={empty ? 'color: var(--muted);' : ''}>{row}</div>,
            ...grid.cols.map((col, c) => (
              <div class={`cell ${empty ? 'zero' : ''}`} key={`${row}-${col}`}>
                {grid.cells[r][c] ? <Bubble n={grid.cells[r][c]} /> : <span class="nothing" />}
              </div>
            )),
          ]
        })}
      </div>

      <div class="note">An empty circle means nothing was placed there, not that nothing exists.</div>
    </>
  )
}
