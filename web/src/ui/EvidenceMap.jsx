import { useState } from "preact/hooks";
import { buildGrid } from "../derive.js";
import { Breakable } from "./text.jsx";

// Area carries the count, so the diameter goes as its square root.
const diameter = (n) => Math.round(13.9 * Math.sqrt(n));

const Bubble = ({ n }) => {
  const size = diameter(n);
  const font = size >= 46 ? 13 : size >= 40 ? 12 : size >= 34 ? 11.5 : 10.5;
  return (
    <span
      class="bubble"
      style={`width: ${size}px; height: ${size}px; font-size: ${font}px;`}
    >
      {n}
    </span>
  );
};

const Axis = ({ label, value, options, onChange }) => (
  <label class="axis">
    <span class="lab">{label}</span>
    <select
      class="field"
      value={String(value)}
      onInput={(event) => onChange(Number(event.currentTarget.value))}
    >
      {options.map((dimension, index) => (
        <option key={dimension.name} value={String(index)}>
          {dimension.name}
        </option>
      ))}
    </select>
  </label>
);

export function EvidenceMap({ map, included, community }) {
  const [axes, setAxes] = useState({ row: 0, col: 1 });
  const [facet, setFacet] = useState(null);
  const grid = buildGrid(map, { ...axes, facet });
  if (!grid) return <div class="note">No map yet.</div>;

  // Picking an axis that is already in use swaps the two, so there is always a
  // valid pair and nothing to validate.
  const pick = (which) => (index) =>
    setAxes(({ row, col }) => {
      const other = which === "row" ? col : row;
      const swapped = index === other ? (which === "row" ? row : col) : other;
      setFacet(null);
      return which === "row"
        ? { row: index, col: swapped }
        : { row: swapped, col: index };
    });

  const unplaced = included == null ? null : included - grid.total;
  return (
    <>
      <div class="map-head">
        <div class="map-title">
          {grid.rowDim.name} by {grid.colDim.name.toLowerCase()}
        </div>
        <div style="font-size: 12px; color: var(--muted); margin-top: 5px;">
          {grid.placed} placed
          {unplaced > 0 ? `. ${unplaced} could not be placed.` : "."}
        </div>
      </div>

      <div class="map-controls">
        <Axis
          label="Rows"
          value={grid.rowIndex}
          options={map.dimensions}
          onChange={pick("row")}
        />
        <Axis
          label="Columns"
          value={grid.colIndex}
          options={map.dimensions}
          onChange={pick("col")}
        />
        <div class="facets">
          <span class="lab">{grid.facetDim.name}</span>
          <button
            type="button"
            class={`facet ${facet ? "" : "on"}`}
            onClick={() => setFacet(null)}
          >
            <span>All</span>
            <span class="facet-n">{grid.total}</span>
          </button>
          {grid.facets.map((option) => (
            <button
              type="button"
              key={option.name}
              class={`facet ${facet === option.name ? "on" : ""}`}
              onClick={() =>
                setFacet(facet === option.name ? null : option.name)
              }
            >
              <span>
                <Breakable>{option.name}</Breakable>
              </span>
              <span class="facet-n">{option.count}</span>
            </button>
          ))}
        </div>
      </div>

      <figure class="map-figure">
        <div class="grid-scroll">
          <div
            class="grid"
            style={`grid-template-columns: 200px repeat(${grid.cols.length}, minmax(110px, 1fr));`}
          >
            <div class="corner" />
            {grid.cols.map((col) => (
              <div class="head col-head" key={col}>
                <Breakable>{col}</Breakable>
              </div>
            ))}
            {grid.rows.map((row, r) => {
              const empty = grid.cells[r].every((n) => n === 0);
              return [
                <div class={`head row-head ${empty ? "faded" : ""}`} key={row}>
                  <Breakable>{row}</Breakable>
                </div>,
                ...grid.cols.map((col, c) => (
                  <div
                    class={`cell ${empty ? "zero" : ""}`}
                    key={`${row}-${col}`}
                  >
                    {grid.cells[r][c] ? (
                      <Bubble n={grid.cells[r][c]} />
                    ) : (
                      <span class="nothing" />
                    )}
                  </div>
                )),
              ];
            })}
          </div>
        </div>
        {/* Inside the figure, not the page: the way this map travels is as a
          screenshot cropped to the grid, and a caveat outside the crop is a
          caveat that does not travel with it. */}
        <figcaption class="map-caption">
          An empty cell means no screened reference from the{" "}
          {community.toUpperCase()} repository was placed there.
        </figcaption>
      </figure>
    </>
  );
}
