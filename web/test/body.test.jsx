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
    expect(html).toContain('LLM reasoning:')
  })

  it('says so plainly when a completed step has nothing to show', () => {
    const html = render(
      <Body row={row({ type: 'retrieve_sparse_evidence', operation: { id: 'o4' } })} artifact={() => null} onAnswer={noop} />,
    )
    expect(html).toContain('Nothing to show')
  })
})
