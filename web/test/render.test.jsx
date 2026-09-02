import { describe, expect, it } from 'vitest'
import render from 'preact-render-to-string'
import { Panel } from '../src/ui/Panel.jsx'
import { Reasoning } from '../src/ui/Reasoning.jsx'
import { Tick, Info } from '../src/ui/Icons.jsx'
import { Disclaimer } from '../src/ui/Disclaimer.jsx'
import { Breakable } from '../src/ui/text.jsx'
import { Chrome } from '../src/ui/Chrome.jsx'
import { Body } from '../src/ui/Session.jsx'
import { ForkButton, ForkConfirm } from '../src/ui/Fork.jsx'
import { Questions } from '../src/ui/Questions.jsx'
import { Sessions } from '../src/ui/Sessions.jsx'
import { References, stepReferences, Why } from '../src/ui/References.jsx'
import { SLICES } from '../src/derive.js'
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
    expect(html).toContain('Model reasoning')
    expect(html).toContain('One search per barrier family.')
  })

  it('renders nothing when there is no reasoning', () => {
    expect(render(<Reasoning text="" />)).toBe('')
  })

  it('names which decision it explains, where a view shows more than one', () => {
    const html = render(
      <Reasoning label="Model reasoning: mapping" text="Urban cohort." />,
    )
    expect(html).toContain('Model reasoning: mapping')
  })
})

// Pairs, not an object: engine.views.Ordered serialises it this way so jsonb
// keeps the order.
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

  it('offers a new question where a view asks for it', () => {
    useAdapter(null)
    expect(render(<Chrome onNewQuestion={() => {}} />)).toContain('Ask a new question')
  })

  // The session list already has the button in its own head, so the topbar
  // would be showing it twice.
  it('leaves the topbar alone where a view does not', () => {
    useAdapter(null)
    expect(render(<Chrome />)).not.toContain('Ask a new question')
  })
})

describe('disclaimer', () => {
  it('has copy in every section', () => {
    expect(render(<Disclaimer mode="review" />)).not.toContain('terms-todo')
  })

  it('marks an unwritten destination rather than linking nowhere', () => {
    // Both outward links are unset. They must read as gaps, not as text that
    // happens to look ordinary — a silent placeholder is how one ships.
    const html = render(<Disclaimer mode="review" />)
    expect(html).toContain('terms-unset')
    expect(html).not.toContain('href="#"')
  })
})

describe('References', () => {
  const rows = [
    {
      destiny_id: 'aaa',
      stage: 'excluded',
      provenance: [{ mode: 'sparse', query: 'hpv uptake' }],
      screening: { include: false, reasoning: 'high-income only' },
      coordinate: null,
      mapping: null,
      evidence: { title: 'Barriers in Kenya', authors: ['Smith', 'Jones'], year: 2019 },
    },
    {
      destiny_id: 'bbb',
      stage: 'mapped',
      provenance: [],
      screening: { include: true, reasoning: 'reports uptake' },
      coordinate: { Setting: ['Urban'] },
      mapping: { dimensions_version: 1, reasoning: 'urban cohort' },
      evidence: null,
    },
  ]

  it('waits on a spinner rather than an empty table', () => {
    const html = render(<References references={null} community="hpv" loading />)
    expect(html).toContain('spinner')
    expect(html).not.toContain('ref-list')
  })

  it('keeps the reasoning behind the row, not in the collapsed list', () => {
    const html = render(<References references={rows} community="hpv" />)
    expect(html).toContain('ref-list')
    expect(html).not.toContain('high-income only')
  })

  it('lists every stage, with the title, authors and year', () => {
    const html = render(<References references={rows} community="hpv" />)
    expect(html).toContain('Barriers in Kenya')
    expect(html).toContain('Smith et al.')
    expect(html).toContain('2019')
    expect(html).toContain('excluded')
    expect(html).toContain('mapped')
  })

  it('links each reference into the repository under its community', () => {
    const html = render(<References references={rows} community="ESEA" />)
    expect(html).toContain('/esea/references/aaa')
  })

  it('names a reference the repository dropped rather than printing its id', () => {
    const html = render(<References references={rows} community="hpv" />)
    expect(html).toContain('Untitled reference')
    expect(html).not.toContain('>bbb<')
  })

  it('reads a placed reference as included when the slice is screening', () => {
    const html = render(
      <References references={rows} community="hpv" slice={SLICES.verdict} />,
    )
    expect(html).toContain('Screening')
    expect(html).toContain('included')
    expect(html).not.toContain('>mapped<')
  })

  it('sits inside a step without a section rule of its own', () => {
    const html = render(<References references={rows} community="hpv" inset />)
    expect(html).toContain('refs inset')
    expect(html).not.toContain('map-title')
  })

  it('says what a cell selection narrowed the list to', () => {
    const html = render(
      <References
        references={rows}
        community="hpv"
        cell={{ key: 'k', label: 'Urban × Mortality', terms: [['Setting', 'Urban']] }}
      />,
    )
    expect(html).toContain('1 of 2')
    expect(html).toContain('Urban × Mortality')
    expect(html).not.toContain('Barriers in Kenya')
  })

  describe('a row’s detail', () => {
    const reference = {
      destiny_id: 'bbb',
      provenance: [{ mode: 'sparse', query: 'hpv uptake' }],
      screening: { include: true, reasoning: 'reports uptake' },
      coordinate: { Setting: ['Urban'] },
      mapping: { reasoning: 'urban cohort' },
      evidence: { title: 'Uptake in Nairobi' },
    }

    it('keeps to the reasoning the view is about', () => {
      const screening = render(
        <Why reference={reference} shows={['screening', 'found']} />,
      )
      expect(screening).toContain('reports uptake')
      expect(screening).not.toContain('urban cohort')
      expect(screening).toContain('hpv uptake')

      const mapping = render(
        <Why reference={reference} shows={['mapping', 'coordinate']} />,
      )
      expect(mapping).toContain('urban cohort')
      expect(mapping).toContain('Urban')
      expect(mapping).not.toContain('reports uptake')
    })

    it('shows the lot where the whole pipeline is on display', () => {
      const html = render(<Why reference={reference} />)
      expect(html).toContain('reports uptake')
      expect(html).toContain('urban cohort')
      expect(html).toContain('hpv uptake')
    })
  })

  describe('a step’s own slice of it', () => {
    const refs = (extra = {}) => ({ references: rows, community: 'hpv', loading: false, ...extra })

    it('reads screening through its verdicts, placed references included', () => {
      const html = render(stepReferences('screen_evidence', refs()))
      expect(html).toContain('Screening')
      expect(html).toContain('All 2.')
    })

    it('shows mapping only what screening kept', () => {
      const html = render(stepReferences('generate_map', refs()))
      expect(html).toContain('Mapping')
      expect(html).toContain('All 1.')
      expect(html).not.toContain('Barriers in Kenya')
    })

    it('says the references are coming rather than showing untitled rows', () => {
      const html = render(
        stepReferences('screen_evidence', refs({ references: null, loading: true })),
      )
      expect(html).toContain('spinner')
      expect(html).not.toContain('ref-list')
    })

    it('gives a step with no table, or no references, nothing', () => {
      expect(stepReferences('enhance_sparse_query', refs())).toBeNull()
      expect(stepReferences('screen_evidence', refs({ references: [] }))).toBeNull()
    })

    it('keeps a retrieval step to what it found, with no downstream state on it', () => {
      const found = [
        { ...rows[0], stage: 'excluded', provenance: [{ mode: 'taxonomy', filters: [] }] },
      ]
      const html = render(
        stepReferences('retrieve_concept_evidence', refs({ references: found })),
      )
      expect(html).toContain('Barriers in Kenya')
      expect(html).not.toContain('ref-stage')
      expect(html).not.toContain('facet')
    })
  })
})

describe('Fork', () => {
  it('says it makes a new session, not that it edits this one', () => {
    const html = render(<ForkButton onFork={() => {}} />)
    expect(html).toContain('Answer differently in a new session')
  })

  it('offers a fork per question when a step asked several', () => {
    const html = render(
      <Questions
        onFork={() => {}}
        decisions={[
          { id: 'a', key: 'clarify:2', prompt: 'first?', options: [], answer: [] },
          { id: 'b', key: 'clarify:4', prompt: 'second?', options: [], answer: [] },
        ]}
      />,
    )
    expect(html.match(/Answer differently in a new session/g)).toHaveLength(2)
  })

  it('says what it will do before it does it', () => {
    const html = render(
      <ForkConfirm
        question="Which of these criteria should we apply?"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(html).toContain('creates a new session from this point')
    // Names the question, so forking the second of several is unambiguous.
    expect(html).toContain('Which of these criteria should we apply?')
    expect(html).toContain('Cancel')
  })
})

describe('Sessions', () => {
  const session = (extra = {}) => ({
    id: 'a',
    question: 'Does X affect Y?',
    community: 'hpv',
    created_at: '2026-09-02T00:00:00Z',
    forked_from_id: null,
    ...extra,
  })

  it('marks forks and leaves originals alone', () => {
    const plain = render(<Sessions sessions={[session()]} onOpen={() => {}} onNew={() => {}} />)
    const forked = render(
      <Sessions sessions={[session({ forked_from_id: 'b' })]} onOpen={() => {}} onNew={() => {}} />,
    )
    expect(plain).not.toContain('fork-mark')
    expect(forked).toContain('fork-mark')
  })
})

describe('Suggest again', () => {
  const row = (extra = {}) => ({
    type: 'enhance_sparse_query',
    title: 'Draft search queries',
    state: 'ask',
    questions: [],
    operation: { id: 'op', decisions: [], pending_questions: [] },
    ...extra,
  })

  it('offers regeneration on a step that suggests', () => {
    const html = render(
      <Body row={row({ regenerate: true })} artifact={() => null} refs={{}} onAnswer={() => {}} />,
    )
    expect(html).toContain('Suggest again')
  })

  it('does not offer it on a step that does not', () => {
    const html = render(<Body row={row()} artifact={() => null} refs={{}} onAnswer={() => {}} />)
    expect(html).not.toContain('Suggest again')
  })
})

describe('Questions', () => {
  const decision = (key, prompt, chosen) => ({
    id: key,
    key,
    prompt,
    options: [
      { id: '0', label: 'Detection', value: { option: 'Detection' } },
      { id: '1', label: 'None of these', value: { option: 'None of these' } },
    ],
    answer: chosen,
  })

  const two = [
    decision('clarify:2', 'Which strategies?', [{ option: 'None of these' }]),
    decision('clarify:4', 'Which aspects?', [{ option: 'Detection' }]),
  ]

  it('shows each question, what was chosen, and why it was asked', () => {
    const html = render(
      <Questions decisions={two} trajectory={[['thought_2', 'narrowing the scheme']]} onFork={() => {}} />,
    )
    expect(html).toContain('Which strategies?')
    expect(html).toContain('None of these')
    // The thought behind the question, read out of the trajectory by its key.
    expect(html).toContain('narrowing the scheme')
  })

  it('has nothing to say about a step that answered nothing', () => {
    expect(render(<Questions decisions={[]} onFork={() => {}} />)).toBe('')
  })
})
