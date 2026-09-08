import { Tick, Pause, Cross, Chevron, Spinner } from "./Icons.jsx";

const GLYPH = {
  done: <Tick />,
  running: <Spinner colour="#2b2a27" size={17} />,
  ask: <Pause />,
  failed: <Cross />,
  todo: null,
};

export const Pip = ({ state }) => (
  <span class={`pip ${state}`}>{GLYPH[state]}</span>
);

export const Toggle = ({ open }) => (
  <span class={`toggle ${open ? "on" : ""}`}>
    <Chevron up={open} colour={open ? "#4a4843" : "#86837c"} />
  </span>
);

/**
 * One step. Collapsed it is a single line.
 */
export function Panel({
  state,
  title,
  summary,
  open,
  onToggle,
  action = null,
  children,
}) {
  const collapsible = state !== "todo" && children;
  const classes = ["step", state, open && collapsible ? "open" : ""]
    .filter(Boolean)
    .join(" ");
  const Head = collapsible ? "button" : "div";
  return (
    <div class={classes}>
      {/* The head is its own button, so `action` can be one too. */}
      <div class="step-bar">
        <Head
          class="step-head"
          type={collapsible ? "button" : undefined}
          onClick={collapsible ? onToggle : undefined}
        >
          <Pip state={state} />
          <span class="step-title">{title}</span>
          <span class="step-summary">{summary}</span>
        </Head>
        {action}
        {collapsible ? (
          <button
            type="button"
            class="step-toggle"
            aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
            onClick={onToggle}
          >
            <Toggle open={open} />
          </button>
        ) : null}
      </div>
      {open && collapsible ? <div class="step-body">{children}</div> : null}
    </div>
  );
}
