import { describe, expect, it } from 'vitest'
import render from 'preact-render-to-string'
import { EditList, repeated } from '../src/ui/Ask.jsx'

const noop = () => {}

const subtopics = (...names) =>
  names.map((name) => ({ id: name, label: name, value: { name, description: '' } }))

describe('repeated', () => {
  it('lists the values more than one item shares, once each, sorted', () => {
    const items = [{ name: 'School' }, { name: 'Clinic' }, { name: 'School' }, { name: 'Clinic' }]
    expect(repeated(items, 'name')).toEqual(['Clinic', 'School'])
  })

  it('is empty when every value differs', () => {
    expect(repeated([{ name: 'School' }, { name: 'Clinic' }], 'name')).toEqual([])
  })
})

describe('EditList', () => {
  const decision = (options) => ({
    type: 'edit_list',
    options,
    constraints: { min: 2, allow_new: true, unique: 'name' },
  })

  it('refuses to save names that repeat, and says which', () => {
    const html = render(
      <EditList decision={decision(subtopics('School', 'Clinic', 'School'))} onAnswer={noop} saving={false} />,
    )
    expect(html).toContain('names must be unique: School')
    expect(html).toMatch(/<button class="btn" disabled/)
  })

  it('saves distinct names', () => {
    const html = render(
      <EditList decision={decision(subtopics('School', 'Clinic'))} onAnswer={noop} saving={false} />,
    )
    expect(html).not.toContain('must be unique')
    expect(html).not.toMatch(/<button class="btn" disabled/)
  })
})
