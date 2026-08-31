import { describe, expect, it } from 'vitest'
import render from 'preact-render-to-string'
import { Panel } from '../src/ui/Panel.jsx'
import { Reasoning } from '../src/ui/Reasoning.jsx'
import { Trace, iterations } from '../src/ui/Trace.jsx'
import { Tick, Info } from '../src/ui/Icons.jsx'
import { Breakable } from '../src/ui/text.jsx'
import { Chrome } from '../src/ui/Chrome.jsx'
import { useAdapter } from '../src/auth.js'

describe('Panel', () => {
  it('shows its summary and hides its body when collapsed', () => {
    const html = render(
      <Panel state="done" title="Screen the evidence" summary="94 included" open={false}>
        <p>the body</p>
      </Panel>,
    )
    expect(html).toContain('94 included')
    expect(html).not.toContain('the body')
  })

  it('shows the body when open', () => {
    const html = render(
      <Panel state="done" title="Screen the evidence" summary="94 included" open>
        <p>the body</p>
      </Panel>,
    )
    expect(html).toContain('the body')
  })

  it('gives a todo step no control to press', () => {
    const html = render(<Panel state="todo" title="Place evidence" summary="" open={false} />)
    expect(html).not.toContain('<button')
  })
})

describe('Reasoning', () => {
  it('labels model prose so it cannot be read as ours', () => {
    const html = render(<Reasoning text="One search per barrier family." />)
    expect(html).toContain('LLM reasoning')
    expect(html).toContain('One search per barrier family.')
  })

  it('renders nothing when there is no reasoning', () => {
    expect(render(<Reasoning text="" />)).toBe('')
  })
})

const TRAJECTORY = {
  thought_0: 'See how this vocabulary is organised.',
  tool_name_0: 'list_schemes',
  tool_args_0: {},
  observation_0: '["hpv-barriers"]',
  thought_1: 'Ask before committing.',
  tool_name_1: 'ask_for_clarification',
  tool_args_1: { request: { question: 'Barriers to what?' } },
}

describe('Trace', () => {
  it('treats the step with no observation as the one still waiting', () => {
    const rows = iterations({ trajectory: TRAJECTORY })
    expect(rows).toHaveLength(2)
    expect(rows[0].pending).toBe(false)
    expect(rows[1].pending).toBe(true)
    expect(rows[0].call).toBe('list_schemes()')
  })

  it('is collapsed to a single control until opened', () => {
    const html = render(<Trace payload={{ trajectory: TRAJECTORY }} />)
    expect(html).toContain('2 steps')
    expect(html).not.toContain('list_schemes()')
  })

  it('renders nothing for an operation with no trajectory', () => {
    expect(render(<Trace payload={null} />)).toBe('')
  })
})

describe('Breakable', () => {
  it('gives a compound label a break opportunity after each slash', () => {
    const html = render(<Breakable>Channel/Medium/Platform</Breakable>)
    expect(html).toBe('Channel/<wbr/>Medium/<wbr/>Platform')
  })

  it('leaves an ordinary label alone', () => {
    expect(render(<Breakable>Vaccine hesitancy</Breakable>)).toBe('Vaccine hesitancy')
  })
})

describe('icons', () => {
  // Preact passes camelCase props through verbatim on an <svg> root, so
  // strokeLinecap there is dropped without an error and every icon quietly
  // loses its round caps and its stroke width.
  it('kebab-cases stroke attributes on the svg root so they survive', () => {
    const html = render(<Tick />)
    expect(html).toContain('stroke-linecap="round"')
    expect(html).toContain('stroke-width="1.7"')
    expect(html).not.toContain('strokeLinecap')
  })

  it('draws icon dots as circles, not zero-length paths that need a round cap', () => {
    // The ring and the bang's dot. Coordinates are free to move; what must not
    // come back is a dot drawn as a degenerate path, which renders as nothing
    // the moment a round cap is missing.
    const html = render(<Info />)
    expect(html.match(/<circle/g)).toHaveLength(2)
    expect(html).not.toMatch(/d="M([\d.]+) ([\d.]+) L\1 \2"/)
  })
})

describe('Chrome', () => {
  const signedInAs = (tokenParsed) => useAdapter({ tokenParsed })

  it('shows nobody when Keycloak is off, as in development', () => {
    useAdapter(null)
    expect(render(<Chrome />)).not.toContain('Sign out')
  })

  it('names the signed-in user and offers a way out', () => {
    signedInAs({ name: 'Adam Hamilton', email: 'adam@futureevidence.org' })
    const html = render(<Chrome />)
    expect(html).toContain('Adam Hamilton')
    expect(html).toContain('Sign out')
    // The email is the tooltip, not a second line of chrome.
    expect(html).toContain('title="adam@futureevidence.org"')
  })

  it('falls back to the username, then to the email', () => {
    signedInAs({ preferred_username: 'ahamilton' })
    expect(render(<Chrome />)).toContain('ahamilton')
    signedInAs({ email: 'adam@futureevidence.org' })
    expect(render(<Chrome />)).toContain('adam@futureevidence.org')
  })

  it('does not repeat the email as its own tooltip', () => {
    signedInAs({ email: 'adam@futureevidence.org' })
    expect(render(<Chrome />)).not.toContain('title="adam@futureevidence.org"')
  })

  it('stays out of the way when the token names nobody', () => {
    signedInAs({ sub: 'abc' })
    expect(render(<Chrome />)).not.toContain('Sign out')
  })
})
