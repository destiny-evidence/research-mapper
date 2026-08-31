import { Tick, Dot, Pause, Cross, Chevron } from './Icons.jsx'

const GLYPH = {
  done: <Tick />,
  running: <Dot />,
  ask: <Pause />,
  failed: <Cross />,
  todo: null,
}

export const Pip = ({ state }) => <span class={`pip ${state}`}>{GLYPH[state]}</span>

export const Toggle = ({ open }) => (
  <span class={`toggle ${open ? 'on' : ''}`}>
    <Chevron up={open} colour={open ? '#4a4843' : '#86837c'} />
  </span>
)

/**
 * One step. Collapsed it is a single line — title, summary, and a toggle that
 * looks like a control. Everything else, reasoning included, lives inside.
 */
export function Panel({ state, title, summary, open, onToggle, children }) {
  const collapsible = state !== 'todo' && children
  const classes = ['step', state, open && collapsible ? 'open' : ''].filter(Boolean).join(' ')
  const Head = collapsible ? 'button' : 'div'
  return (
    <div class={classes}>
      <Head class="step-head" type={collapsible ? 'button' : undefined} onClick={collapsible ? onToggle : undefined}>
        <Pip state={state} />
        <span class="step-title">{title}</span>
        <span class="step-summary">{summary}</span>
        {collapsible ? <Toggle open={open} /> : null}
      </Head>
      {open && collapsible ? <div class="step-body">{children}</div> : null}
    </div>
  )
}
