import { Fragment } from 'preact'

/**
 * Compound labels like "Channel/Medium" are one long word as far as the browser
 * is concerned, so they overflow rather than wrap. This gives them a break
 * opportunity after each slash and nowhere else — no mid-word hyphenation.
 */
export function Breakable({ children }) {
  const parts = String(children ?? '').split('/')
  if (parts.length === 1) return children ?? null
  return parts.map((part, index) => (
    <Fragment key={index}>
      {index < parts.length - 1 ? (
        <>
          {part}/<wbr />
        </>
      ) : (
        part
      )}
    </Fragment>
  ))
}
