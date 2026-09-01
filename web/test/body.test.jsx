import { describe, expect, it } from 'vitest'
import render from 'preact-render-to-string'
import { Body } from '../src/ui/Session.jsx'

const noop = () => {}
const row = (extra) => ({ type: 'screen_evidence', state: 'done', questions: [], ...extra })

describe('step body', () => {
  it('offers a retry and shows the error a failed operation carries', () => {
    const html = render(
      <Body
        row={row({
          state: 'failed',
          operation: { id: 'o1', error: { message: 'vocabulary fetch returned 503' } },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('vocabulary fetch returned 503')
    expect(html).toContain('Retry')
  })

  it('asks every open question, not just the first', () => {
    const questions = [
      { id: 1, key: 'barrier', type: 'edit_list', prompt: 'Edit the subtopics of Barrier.', options: [], constraints: { min: 1, allow_new: true } },
      { id: 2, key: 'setting', type: 'edit_list', prompt: 'Edit the subtopics of Setting.', options: [], constraints: { min: 1, allow_new: true } },
    ]
    const html = render(
      <Body
        row={row({
          type: 'generate_map_subtopics',
          state: 'ask',
          questions,
          operation: { id: 'o2', decisions: [...questions, { id: 3, answer: [{}] }] },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('Edit the subtopics of Barrier.')
    expect(html).toContain('Edit the subtopics of Setting.')
    expect(html).toContain('1 of 3 saved')
  })

  it('shows the suggestion’s reasoning while the question is still open', () => {
    const questions = [{ id: 1, key: 'select_queries', type: 'select_many', prompt: 'Which searches?', options: [], constraints: {} }]
    const html = render(
      <Body
        row={row({
          type: 'enhance_sparse_query',
          state: 'ask',
          questions,
          operation: { id: 'o7', decisions: questions },
        })}
        artifact={(type) =>
          type === 'suggested_search_queries' ? { reasoning: 'One search per barrier family.' } : null
        }
        onAnswer={noop}
      />,
    )
    expect(html).toContain('Model reasoning')
    expect(html).toContain('One search per barrier family.')
  })

  it('renders the artifact a completed step produced', () => {
    const payload = { queries: [{ query: 'hesitanc* AND HPV' }], reasoning: 'One search per family.' }
    const html = render(
      <Body
        row={row({ type: 'enhance_sparse_query', operation: { id: 'o3' } })}
        artifact={(type) => (type === 'search_queries' ? payload : null)}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('hesitanc* AND HPV')
    expect(html).toContain('Model reasoning')
  })

  it('shows a working bar and no counter when a step has nothing to count', () => {
    const html = render(
      <Body
        row={row({
          type: 'enhance_sparse_query',
          state: 'running',
          operation: { id: 'o5', status: 'running', progress: { done: 0, total: null, failed: 0 } },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('bar working')
    expect(html).toContain('Thinking')
    expect(html).not.toContain('class="counts"')
  })

  it('counts only once there is a total to count against', () => {
    const html = render(
      <Body
        row={row({
          state: 'running',
          operation: { id: 'o6', status: 'running', progress: { done: 254, total: 530, failed: 3 } },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('254 of 530')
    expect(html).toContain('3 failed')
    expect(html).not.toContain('bar working')
  })

  it('shows what a step produced even when it has no artifact to render', () => {
    const html = render(
      <Body
        row={row({
          type: 'screen_evidence',
          operation: { id: 'o8', result: { screened: 530, included: 94, failed: 3, version: 2 } },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('screened')
    expect(html).toContain('530')
    // version is plumbing, not a result
    expect(html).not.toContain('version')
  })

  it('falls back to the suggestion when the step never captured its reasoning', () => {
    // generate_map_subtopics writes Dimensions without a reasoning field.
    const html = render(
      <Body
        row={row({ type: 'generate_map_subtopics', operation: { id: 'o9', result: {} } })}
        artifact={(type) =>
          type === 'dimensions'
            ? { dimensions: [{ name: 'Barrier', description: '', subtopics: [] }], reasoning: '' }
            : type === 'suggested_dimension_subtopics'
              ? { reasoning: 'Three dimensions that cut across each other.' }
              : null
        }
        onAnswer={noop}
      />,
    )
    expect(html).toContain('Three dimensions that cut across each other.')
  })

  it('offers both ways to build the map at the branch', () => {
    const html = render(
      <Body
        row={row({
          type: 'choose-how-to-map',
          state: 'ask',
          branch: {
            suggested: { head: 'generate_map_dimensions', label: 'Let it suggest dimensions', detail: 'a' },
            taxonomy: { head: 'generate_taxonomy_map', label: "Use the taxonomy's own schemes", detail: 'b' },
          },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('Let it suggest dimensions')
    expect(html).toContain('Use the taxonomy')
  })

  it('offers the other approach when a mapping step fails, since retrying will not help', () => {
    const html = render(
      <Body
        row={row({
          type: 'generate_taxonomy_map',
          state: 'failed',
          operation: { id: 'o10', error: { message: 'annotated against 1 taxonomy scheme(s)' } },
        })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('annotated against 1 taxonomy scheme(s)')
    expect(html).toContain('Retry')
    expect(html).toContain('Let it suggest dimensions')
  })

  it('offers no such switch when an ordinary step fails', () => {
    const html = render(
      <Body
        row={row({ state: 'failed', operation: { id: 'o11', error: { message: 'boom' } } })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )
    expect(html).toContain('Retry')
    expect(html).not.toContain('taxonomy')
  })

  it('says so plainly when a completed step has nothing to show', () => {
    const html = render(
      <Body row={row({ type: 'retrieve_sparse_evidence', operation: { id: 'o4' } })} artifact={() => null} onAnswer={noop} />,
    )
    expect(html).toContain('Nothing to show')
  })
})

describe('edit list', () => {
  const decision = (options) => ({
    id: 1,
    key: 'dimensions',
    type: 'edit_list',
    prompt: 'Edit the dimensions.',
    options,
    constraints: { min: 1, allow_new: true },
  })

  const untouched = (options) =>
    render(
      <Body
        row={row({ state: 'ask', type: 'generate_map_dimensions', operation: { id: 'o1', decisions: [] }, questions: [decision(options)] })}
        artifact={() => null}
        onAnswer={noop}
      />,
    )

  it('names accepting the model list as its own act rather than calling it a save', () => {
    const html = untouched([{ id: 'a', value: { name: 'Setting' } }, { id: 'b', value: { name: 'Channel' } }])
    expect(html).toContain('Accept all 2')
    expect(html).not.toContain('>Save<')
  })
})

describe('edit list rationale', () => {
  const withDescriptions = render(
    <Body
      row={row({
        state: 'ask',
        type: 'generate_map_dimensions',
        operation: { id: 'o1', decisions: [] },
        questions: [{
          id: 1,
          key: 'dimensions',
          type: 'edit_list',
          prompt: 'Edit the dimensions.',
          options: [{ id: 'a', value: { name: 'Setting', description: 'Where the study took place.' } }],
          constraints: { min: 1, allow_new: true },
        }],
      })}
      artifact={() => null}
      onAnswer={noop}
    />,
  )

  it("shows each item's own rationale where the choice is made", () => {
    expect(withDescriptions).toContain('Setting')
    expect(withDescriptions).toContain('Where the study took place.')
  })
})

describe('result counts', () => {
  const html = render(
    <Body
      row={row({ state: 'done', type: 'retrieve_sparse_evidence', operation: { result: { queries: 4, failed: 1, references: 212 } } })}
      artifact={() => null}
      onAnswer={noop}
    />,
  )

  it('reads what the step produced before what went wrong with it', () => {
    expect(html.indexOf('references')).toBeLessThan(html.indexOf('failed'))
  })

  it('marks the failure count as a problem rather than a plain number', () => {
    expect(html).toContain('class="bad"')
  })
})
