import { useState } from "preact/hooks";
import { buildGrid, cellKey } from "../derive.js";
import { Breakable } from "./text.jsx";

// The cell is 70px tall, so the largest bubble has to stay inside that
const MIN = 22;
const MAX = 62;

const diameter = (n, max) => {
  if (n <= 0) return 0;
  if (max <= 1) return MAX;
  const fraction = (Math.sqrt(n) - 1) / (Math.sqrt(max) - 1);
  return Math.round(MIN + (MAX - MIN) * fraction);
};

const compact = new Intl.NumberFormat(undefined, { notation: "compact" });

const Bubble = ({ n, max }) => {
  const size = diameter(n, max);
  const font = size >= 46 ? 13 : size >= 40 ? 12 : size >= 34 ? 11.5 : 10.5;
  return (
    <span
      class="bubble"
      title={String(n)}
      style={`width: ${size}px; height: ${size}px; font-size: ${font}px;`}
    >
      {compact.format(n)}
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

export function EvidenceMap({ map, included, selected, onSelectCell }) {
  const [axes, setAxes] = useState({ row: 0, col: 1 });
  const [facet, setFacet] = useState(null);
  const grid = buildGrid(map, { ...axes, facet });
  if (!grid) return <div class="note">No map yet.</div>;

  // Picking an axis that is already in use swaps the two. The current selection
  // names subtopics from the old axes, so it cannot survive the change.
  const pick = (which) => (index) =>
    setAxes(({ row, col }) => {
      const other = which === "row" ? col : row;
      const swapped = index === other ? (which === "row" ? row : col) : other;
      setFacet(null);
      onSelectCell?.(null);
      return which === "row"
        ? { row: index, col: swapped }
        : { row: swapped, col: index };
    });

  // A cell is the pair of axis subtopics, narrowed by the facet if one is on.
  const termsFor = (row, col) => [
    [grid.rowDim.name, row],
    [grid.colDim.name, col],
    ...(facet ? [[grid.facetDim.name, facet]] : []),
  ];

  const select = (row, col) => {
    const terms = termsFor(row, col);
    const key = cellKey(terms);
    if (key === selected) return onSelectCell?.(null);
    onSelectCell?.({
      key,
      terms,
      label: [row, col, facet].filter(Boolean).join(" × "),
    });
  };

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
            onClick={() => {
              setFacet(null);
              onSelectCell?.(null);
            }}
          >
            <span>All</span>
            <span class="facet-n">{grid.total}</span>
          </button>
          {grid.facets.map((option) => (
            <button
              type="button"
              key={option.name}
              class={`facet ${facet === option.name ? "on" : ""}`}
              onClick={() => {
                setFacet(facet === option.name ? null : option.name);
                onSelectCell?.(null);
              }}
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
                      <button
                        type="button"
                        class={`bubble-hit ${
                          cellKey(termsFor(row, col)) === selected ? "on" : ""
                        }`}
                        onClick={() => select(row, col)}
                        aria-label={`${grid.cells[r][c]} references in ${row} by ${col}`}
                      >
                        <Bubble n={grid.cells[r][c]} max={grid.maxCount} />
                      </button>
                    ) : (
                      <span class="nothing" />
                    )}
                  </div>
                )),
              ];
            })}
          </div>
        </div>
      </figure>
    </>
  );
}
