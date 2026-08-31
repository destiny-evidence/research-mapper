/** Special handling of ResumableReAct trajectories. */

import { useState } from "preact/hooks";
import { Toggle } from "./Panel.jsx";
import { Reasoning } from "./Reasoning.jsx";

const brief = (value, limit = 220) => {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text && text.length > limit ? `${text.slice(0, limit)}…` : text;
};

const callOf = (tool, args) =>
  `${tool}(${Object.entries(args ?? {})
    .map(([name, value]) => `${name}=${brief(value, 60)}`)
    .join(", ")})`;

export function iterations(payload) {
  const { trajectory = {} } = payload ?? {};
  const rows = [];
  for (let i = 0; trajectory[`thought_${i}`] !== undefined; i += 1) {
    const observation = trajectory[`observation_${i}`];
    rows.push({
      index: i,
      thought: trajectory[`thought_${i}`],
      call: callOf(trajectory[`tool_name_${i}`], trajectory[`tool_args_${i}`]),
      observation,
      pending: observation === undefined,
    });
  }
  return rows;
}

const failed = (observation) =>
  typeof observation === "string" &&
  observation.startsWith("Execution error in");

export function Trace({ payload }) {
  const rows = iterations(payload);
  const [open, setOpen] = useState(false);
  if (!rows.length) return null;
  return (
    <div class="trace">
      <button
        type="button"
        class="trace-row"
        style="border-bottom: 0;"
        onClick={() => setOpen(!open)}
      >
        <Toggle open={open} />
        <span style="font-size: 12.5px;">How it got here</span>
        <span class="mono" style="font-size: 11px; color: var(--dim);">
          {rows.length} steps
        </span>
      </button>
      {open
        ? rows.map((row) =>
            row.pending ? (
              <Pending key={row.index} row={row} />
            ) : (
              <Finished key={row.index} row={row} />
            ),
          )
        : null}
    </div>
  );
}

function Finished({ row }) {
  const [open, setOpen] = useState(false);
  const bad = failed(row.observation);
  return (
    <>
      <button type="button" class="trace-row" onClick={() => setOpen(!open)}>
        <span class="trace-idx">{row.index}</span>
        <span class={`call ${bad ? "bad" : ""}`}>{row.call}</span>
        <Toggle open={open} />
      </button>
      {open ? (
        <div style="padding: 4px 0 10px 26px;">
          <div style="font-family: var(--serif); font-size: 11.5px; color: #8a867e;">
            {row.thought}
          </div>
          <div
            class={`obs ${bad ? "bad" : ""}`}
            style={bad ? "color: var(--red);" : ""}
          >
            {brief(row.observation)}
          </div>
        </div>
      ) : null}
    </>
  );
}

function Pending({ row }) {
  return (
    <div class="trace-open">
      <span class="trace-idx" style="color: var(--amber);">
        {row.index}
      </span>
      <div style="flex-grow: 1;">
        <Reasoning text={row.thought} />
        <div class="call" style="margin-top: 7px;">
          {row.call}
        </div>
        <div class="obs pending">waiting</div>
      </div>
    </div>
  );
}
