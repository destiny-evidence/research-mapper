import { describe, expect, it } from 'vitest'
import render from 'preact-render-to-string'
import { Panel } from '../src/ui/Panel.jsx'
import { Reasoning } from '../src/ui/Reasoning.jsx'
import { Trace, iterations } from '../src/ui/Trace.jsx'

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
    expect(html).toContain('LLM reasoning:')
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
