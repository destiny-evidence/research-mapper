import { describe, expect, it, vi } from 'vitest'
import { copy } from '../src/clipboard.js'

/** Just enough DOM for the fallback path. */
const fakeDocument = (copied) => ({
  body: { appendChild: () => {} },
  createElement: () => ({
    style: {},
    setAttribute: () => {},
    select: () => {},
    remove: () => {},
  }),
  execCommand: (command) => {
    copied.push(command)
    return true
  },
})

describe('copy', () => {
  it('uses the clipboard API when there is one', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    const ok = await copy('a link', { navigator: { clipboard: { writeText } } })
    expect(ok).toBe(true)
    expect(writeText).toHaveBeenCalledWith('a link')
  })

  it('falls back to a selection when the clipboard API refuses', async () => {
    const copied = []
    const ok = await copy('a link', {
      navigator: { clipboard: { writeText: () => Promise.reject(new Error('denied')) } },
      document: fakeDocument(copied),
    })
    expect(ok).toBe(true)
    expect(copied).toEqual(['copy'])
  })

  it('says so rather than throwing when neither way works', async () => {
    expect(await copy('a link', { navigator: {} })).toBe(false)
  })
})
