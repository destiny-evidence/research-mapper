import { describe, expect, it } from 'vitest'
import { feedbackUrl } from '../src/feedback.js'

const TEMPLATE =
  'https://docs.google.com/forms/d/e/FORM/viewform?usp=pp_url' +
  '&entry.111={url}&entry.222={question}'

describe('feedbackUrl', () => {
  it('fills in every placeholder the template carries', () => {
    const url = feedbackUrl(
      { url: 'https://mapper.example/#/session/abc', question: 'What works?' },
      TEMPLATE,
    )
    expect(url).toContain('entry.111=https%3A%2F%2Fmapper.example%2F%23%2Fsession%2Fabc')
    expect(url).toContain('entry.222=What%20works%3F')
  })

  it('leaves a field it was given nothing for empty', () => {
    expect(feedbackUrl({}, TEMPLATE)).toMatch(/entry\.111=&entry\.222=$/)
  })

  it('has no address to offer when the form is not configured', () => {
    expect(feedbackUrl({ url: 'https://mapper.example/' }, '')).toBe(null)
  })
})
